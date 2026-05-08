"""会话级消息存储 — 基于 SessionManager 的实现。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory.session import SessionManager

logger = logging.getLogger(__name__)


class MemoryStorage:
    """会话级消息存储。

    保持与旧版相同的公共 API（add_message, get_history, clear, save），
    内部委托给 SessionManager。
    """

    def __init__(self, session_manager: SessionManager, session_id: str) -> None:
        self._session_mgr = session_manager
        self._session_id = session_id
        # 尝试从磁盘加载已有 session 历史；若 session 文件不存在则初始化为空；
        # 若文件损坏则隔离（quarantine）原文件后初始化为空
        try:
            self._messages: list[dict[str, Any]] = session_manager.load_session(session_id)
        except FileNotFoundError:
            self._messages = []
        except ValueError:
            # 损坏文件：重命名为 .corrupt 保留现场，避免 save() 覆盖导致数据不可恢复
            self._quarantine_corrupt_file(session_manager, session_id)
            self._messages = []

    @staticmethod
    def _quarantine_corrupt_file(session_manager: SessionManager, session_id: str) -> None:
        """将损坏的 session 文件重命名为 session-<id>.json.corrupt。"""
        session_path: Path = session_manager._sessions_dir / f"session-{session_id}.json"
        corrupt_path: Path = session_manager._sessions_dir / f"session-{session_id}.json.corrupt"
        try:
            session_path.rename(corrupt_path)
            logger.warning(
                "Corrupt session file quarantined: %s -> %s",
                session_path.name, corrupt_path.name,
            )
        except OSError:
            # rename 失败时不阻塞系统运行，仅记录日志
            logger.warning(
                "Failed to quarantine corrupt session file: %s", session_path.name,
            )

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
