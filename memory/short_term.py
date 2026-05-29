"""短期记忆管理。"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# session_id 严格白名单：仅允许字母、数字、下划线、短横线
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

_EMPTY_SESSION_KEYS = ("session_id", "created", "updated", "items")


class ShortTermMemory:
    """管理短期记忆的读写。每个 session 一个 JSON 文件。"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = (data_dir / "short-term").resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        """返回 session 文件路径，校验 session_id 防止路径遍历。"""
        if not _SAFE_ID_RE.match(session_id):
            raise ValueError(f"非法 session_id: {session_id!r}")
        path = (self._dir / f"{session_id}.json").resolve()
        if not path.is_relative_to(self._dir):
            raise ValueError(f"路径遍历: {session_id!r}")
        return path

    @staticmethod
    def _empty_session(session_id: str) -> dict:
        return {"session_id": session_id, "created": "", "updated": "", "items": []}

    def _load_session(self, session_id: str) -> dict:
        path = self._session_path(session_id)
        if not path.exists():
            return self._empty_session(session_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("session 文件损坏，返回空: %s", path)
            return self._empty_session(session_id)
        # 校验基本结构
        if not isinstance(data, dict) or "items" not in data:
            logger.warning("session 文件结构异常，返回空: %s", path)
            return self._empty_session(session_id)
        return data

    def _save_session(self, data: dict) -> None:
        """原子写入：先写临时文件，再 rename，防止中断导致数据损坏。"""
        path = self._session_path(data["session_id"])
        content = json.dumps(data, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            # 清理临时文件
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def add_item(self, session_id: str, content: str, source: str, context: str = "") -> None:
        data = self._load_session(session_id)
        now = datetime.now(timezone.utc).isoformat()
        if not data["created"]:
            data["created"] = now
        data["updated"] = now
        data["items"].append({
            "id": str(uuid.uuid4()),
            "content": content,
            "source": source,
            "created": now,
            "context": context,
        })
        self._save_session(data)

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        all_items = []
        for p in sorted(self._dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                sid = data.get("session_id", "")
                for item in data.get("items", []):
                    item["session_id"] = sid
                    all_items.append(item)
            except (json.JSONDecodeError, OSError):
                continue
        all_items.sort(key=lambda x: x.get("created", ""), reverse=True)
        return all_items[:limit]

    def get_by_session(self, session_id: str) -> list[dict[str, Any]]:
        return self._load_session(session_id).get("items", [])

    def remove_items(self, item_ids: list[str]) -> None:
        ids = set(item_ids)
        for p in self._dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                original_len = len(data.get("items", []))
                data["items"] = [i for i in data.get("items", []) if i["id"] not in ids]
                if len(data["items"]) != original_len:
                    self._save_session(data)
            except (json.JSONDecodeError, OSError):
                continue

    def cleanup_sessions(self, session_ids: list[str]) -> None:
        for sid in session_ids:
            path = self._session_path(sid)
            if path.exists():
                path.unlink()
