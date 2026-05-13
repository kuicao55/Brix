"""会话级消息存储 — 基于 SessionManager 的实现。"""
from __future__ import annotations

import logging
import uuid
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
            self._quarantine_corrupt_file(session_manager, session_id)
            self._messages = []
        # 记录加载时的消息数量，用于 save() 时的并发安全合并
        self._base_count: int = len(self._messages)

    @staticmethod
    def _quarantine_corrupt_file(session_manager: SessionManager, session_id: str) -> None:
        """将损坏的 session 文件重命名为 session-<id>.json.corrupt。"""
        # 防御纵深：验证 session_id 是否为合法 UUID，防止路径穿越
        try:
            uuid.UUID(session_id)
        except ValueError:
            logger.warning(
                "Skipping quarantine: invalid session_id %r (not a valid UUID)",
                session_id,
            )
            return

        sessions_dir: Path = session_manager._sessions_dir
        session_path: Path = sessions_dir / f"session-{session_id}.json"
        corrupt_path: Path = sessions_dir / f"session-{session_id}.json.corrupt"

        # 防御纵深：确认解析后的路径在 sessions 目录内
        try:
            session_path.resolve().relative_to(sessions_dir.resolve())
        except ValueError:
            logger.warning(
                "Skipping quarantine: session path escapes sessions directory: %s",
                session_path,
            )
            return

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

    def is_empty_on_disk(self) -> bool:
        """加载时磁盘上是否无消息（用于跳过空 session 的持久化）。"""
        return self._base_count == 0

    def add_message(self, role: str, content: str) -> None:
        self._messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def add_full_message(self, message: dict[str, Any]) -> None:
        """添加完整消息（包含 tool_calls, reasoning_content 等字段）。"""
        msg = dict(message)  # 浅拷贝，避免修改调用方的 dict
        if "timestamp" not in msg:
            msg["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._messages.append(msg)

    def get_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        if limit is None:
            return list(self._messages)
        return list(self._messages[-limit:])

    def clear(self) -> None:
        self._messages.clear()
        # 使用 -1 标记已清空状态，save 时直接写入不合并
        self._base_count = -1

    def save(self) -> None:
        # base_count=-1 表示已清空，使用 direct write 模式（不合并磁盘内容）
        bc = self._base_count if self._base_count >= 0 else None
        actual_count = self._session_mgr.save_session(
            self._session_id, self._messages, base_count=bc
        )
        # 使用合并后的实际数量，防止 stale writer 的 base_count 偏离磁盘状态
        self._base_count = actual_count
