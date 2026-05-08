"""会话管理器 — 负责 session 文件的 CRUD 和索引维护。"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
        """从磁盘加载 sessions 索引。"""
        if not self._index_path.exists():
            return []
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save_index(self, index: list[dict[str, Any]]) -> None:
        """将 sessions 索引写入磁盘。"""
        self._atomic_write_json(self._index_path, index)

    def create_session(self) -> str:
        """创建新会话，返回 UUID 标识符。"""
        self._ensure_dirs()
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

    def save_session(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        """保存会话消息并更新索引。"""
        self._ensure_dirs()
        session_path = self._sessions_dir / f"session-{session_id}.json"
        self._atomic_write_json(session_path, messages)
        # 更新索引
        index = self._load_index()
        now = datetime.now(timezone.utc).isoformat()
        preview = ""
        for msg in messages:
            if msg.get("role") == "user":
                preview = msg.get("content", "")[:100]
                break
        for entry in index:
            if entry["id"] == session_id:
                entry["updated"] = now
                entry["message_count"] = len(messages)
                entry["preview"] = preview
                break
        self._save_index(index)

    def load_session(self, session_id: str) -> list[dict[str, Any]]:
        """加载指定会话的消息列表，不存在则抛出 FileNotFoundError。"""
        session_path = self._sessions_dir / f"session-{session_id}.json"
        if not session_path.exists():
            raise FileNotFoundError(f"Session {session_id} not found")
        return json.loads(session_path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[dict[str, Any]]:
        """返回所有会话的索引列表（最新在前）。"""
        return self._load_index()
