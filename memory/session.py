"""会话管理器 — 负责 session 文件的 CRUD 和索引维护。"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_UUID_LEN = 36


def _validate_session_id(session_id: str) -> None:
    """验证 session_id 是否为合法 UUID 格式，防止路径穿越。"""
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise ValueError(
            f"Invalid session_id: {session_id!r}. Must be a valid UUID."
        )


class SessionManager:
    """管理 session-{uuid}.json 文件和 sessions/index.json 索引。"""

    def __init__(self, data_dir: Path) -> None:
        self._sessions_dir = data_dir / "sessions"
        self._index_path = self._sessions_dir / "index.json"

    def _ensure_dirs(self) -> None:
        """确保 sessions 目录存在。"""
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write_json(self, path: Path, data: Any) -> None:
        """原子写入 JSON 文件：先写临时文件再 rename。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), prefix=".session-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _load_index(self) -> list[dict[str, Any]]:
        """从磁盘加载 sessions 索引。损坏时从 session 文件重建。

        支持两种格式：
        - 格式 A（标准）：`[ {...}, {...} ]`
        - 格式 B（spec 文档）：`{ "sessions": [ {...}, {...} ] }`
        """
        if not self._index_path.exists():
            return self._rebuild_index()
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return self._rebuild_index()
        # 格式 B：dict 包裹
        if isinstance(raw, dict) and "sessions" in raw:
            sessions = raw["sessions"]
            if isinstance(sessions, list):
                raw = sessions
            else:
                return self._rebuild_index()
        # 格式 A：直接是 list
        if not isinstance(raw, list):
            return self._rebuild_index()
        # 验证每个元素是 dict 且包含 "id" 键
        for entry in raw:
            if not isinstance(entry, dict) or "id" not in entry:
                return self._rebuild_index()
        return raw

    def _rebuild_index(self) -> list[dict[str, Any]]:
        """从 sessions 目录中的 session-*.json 文件重建索引。"""
        index: list[dict[str, Any]] = []
        if not self._sessions_dir.exists():
            return []
        for p in sorted(self._sessions_dir.glob("session-*.json")):
            # "session-{uuid}.json" -> "{uuid}"
            stem = p.stem  # "session-{uuid}"
            if not stem.startswith("session-"):
                continue
            sid = stem[len("session-"):]
            # 验证 sid 是否为合法 UUID，跳过非 UUID 文件名
            try:
                uuid.UUID(sid)
            except ValueError:
                continue
            try:
                messages = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            # 验证 messages 是否为 list[dict]；损坏文件跳过
            if not isinstance(messages, list):
                continue
            if not all(isinstance(m, dict) for m in messages):
                continue
            # 取第一条 user 消息作为预览
            preview = ""
            for msg in messages:
                if msg.get("role") == "user":
                    preview = msg.get("content", "")[:100]
                    break
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            index.append({
                "id": sid,
                "created": mtime.isoformat(),
                "updated": mtime.isoformat(),
                "message_count": len(messages),
                "preview": preview,
            })
        # 按修改时间倒序
        index.sort(key=lambda e: e["updated"], reverse=True)
        return index

    def _save_index(self, index: list[dict[str, Any]]) -> None:
        """将 sessions 索引写入磁盘。"""
        self._atomic_write_json(self._index_path, index)

    def _with_index_lock(self, fn):
        """在文件锁保护下执行对索引的读-改-写操作。"""
        self._ensure_dirs()
        lock_path = self._sessions_dir / ".index.lock"
        with open(lock_path, "w") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)

    def create_session(self) -> str:
        """创建新会话，返回 UUID 标识符。在文件锁保护下更新索引。"""
        def _do_create() -> str:
            sid = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            index = self._load_index()
            index.insert(0, {
                "id": sid,
                "created": now,
                "updated": now,
                "message_count": 0,
                "preview": "",
            })
            self._save_index(index)
            return sid
        return self._with_index_lock(_do_create)

    def save_session(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        """保存会话消息并更新索引。在文件锁保护下更新索引。"""
        _validate_session_id(session_id)
        session_path = self._sessions_dir / f"session-{session_id}.json"
        self._atomic_write_json(session_path, messages)
        def _update_index() -> None:
            index = self._load_index()
            now = datetime.now(timezone.utc).isoformat()
            preview = ""
            for msg in messages:
                if msg.get("role") == "user":
                    preview = msg.get("content", "")[:100]
                    break
            found = False
            for entry in index:
                if entry["id"] == session_id:
                    entry["updated"] = now
                    entry["message_count"] = len(messages)
                    entry["preview"] = preview
                    found = True
                    break
            if not found:
                # 索引丢失该条目，重新插入
                index.insert(0, {
                    "id": session_id,
                    "created": now,
                    "updated": now,
                    "message_count": len(messages),
                    "preview": preview,
                })
            self._save_index(index)
        self._with_index_lock(_update_index)

    def load_session(self, session_id: str) -> list[dict[str, Any]]:
        """加载指定会话的消息列表，不存在则抛出 FileNotFoundError。

        若文件内容损坏（非 list[dict]），抛出 ValueError。
        """
        _validate_session_id(session_id)
        session_path = self._sessions_dir / f"session-{session_id}.json"
        if not session_path.exists():
            raise FileNotFoundError(f"Session {session_id} not found")
        data = json.loads(session_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(
                f"Session {session_id} file is corrupted: expected list, got {type(data).__name__}"
            )
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Session {session_id} file is corrupted: "
                    f"expected dict at index {i}, got {type(item).__name__}"
                )
        return data

    def list_sessions(self) -> list[dict[str, Any]]:
        """返回所有会话的索引列表（最新在前）。

        加载索引后交叉校验实际 session 文件：
        - 若存在未被索引覆盖的 session 文件 → 自动重建索引
        - 若索引条目对应的 session 文件已删除 → 移除陈旧条目并持久化
        """
        index = self._load_index()
        self._ensure_dirs()
        indexed_ids = {e["id"] for e in index}
        # 检查是否有 session 文件未被索引覆盖
        for p in self._sessions_dir.glob("session-*.json"):
            stem = p.stem
            if not stem.startswith("session-"):
                continue
            sid = stem[len("session-"):]
            try:
                uuid.UUID(sid)
            except ValueError:
                continue
            if sid not in indexed_ids:
                return self._rebuild_index()
        # 检查索引条目对应的 session 文件是否存在
        # 只检查 message_count > 0 的条目：create_session 创建的空条目
        # 尚无 session 文件，属于正常状态。
        # 陈旧条目清理在文件锁保护下执行，防止与并发 create/save 冲突。
        stale = [
            e for e in index
            if e.get("message_count", 0) > 0
            and not (self._sessions_dir / f"session-{e['id']}.json").exists()
        ]
        if stale:
            def _remove_stale() -> list[dict[str, Any]]:
                fresh_index = self._load_index()
                stale_ids = {e["id"] for e in stale}
                cleaned = [e for e in fresh_index if e["id"] not in stale_ids]
                self._save_index(cleaned)
                return cleaned
            return self._with_index_lock(_remove_stale)
        return index
