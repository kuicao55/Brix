"""会话级消息存储 — 基于 SessionManager 的实现。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from memory.session import SessionManager


class MemoryStorage:
    """会话级消息存储。

    保持与旧版相同的公共 API（add_message, get_history, clear, save），
    内部委托给 SessionManager。
    """

    def __init__(self, session_manager: SessionManager, session_id: str) -> None:
        self._session_mgr = session_manager
        self._session_id = session_id
        self._messages: list[dict[str, Any]] = []

    def add_message(self, role: str, content: str) -> None:
        self._messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        if limit is None:
            return list(self._messages)
        return list(self._messages[-limit:])

    def clear(self) -> None:
        self._messages.clear()

    def save(self) -> None:
        self._session_mgr.save_session(self._session_id, self._messages)
