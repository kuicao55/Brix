"""短期记忆管理。"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """管理短期记忆的读写。每个 session 一个 JSON 文件。"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "short-term"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def _load_session(self, session_id: str) -> dict:
        path = self._session_path(session_id)
        if not path.exists():
            return {"session_id": session_id, "created": "", "updated": "", "items": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"session_id": session_id, "created": "", "updated": "", "items": []}

    def _save_session(self, data: dict) -> None:
        path = self._session_path(data["session_id"])
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

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
                all_items.extend(data.get("items", []))
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
