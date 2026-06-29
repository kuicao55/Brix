"""Session 管理 — per-connection SessionContext。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memory import MemoryProvider, create_memory_provider

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """单个 WebSocket 连接的会话上下文。"""

    client_id: str
    memory: MemoryProvider
    current_session_id: str | None = None


class SessionHandler:
    """管理多个连接的 SessionContext。"""

    def __init__(self, data_dir: Path, max_context_tokens: int = 8000) -> None:
        self._data_dir = data_dir
        self._max_context_tokens = max_context_tokens
        self._contexts: dict[str, SessionContext] = {}

    def create_context(self, client_id: str) -> SessionContext:
        """为新连接创建独立的 SessionContext。"""
        memory = create_memory_provider(
            data_dir=self._data_dir,
            max_context_tokens=self._max_context_tokens,
        )
        ctx = SessionContext(
            client_id=client_id,
            memory=memory,
            current_session_id=None,
        )
        self._contexts[client_id] = ctx
        logger.info("Created session context for client %s", client_id)
        return ctx

    def get_context(self, client_id: str) -> SessionContext | None:
        """获取指定连接的 SessionContext。"""
        return self._contexts.get(client_id)

    def release_context(self, client_id: str) -> None:
        """释放 session 资源。"""
        ctx = self._contexts.pop(client_id, None)
        if ctx:
            ctx.memory.save_session()
            logger.info("Released session context for client %s", client_id)

    def get_all_contexts(self) -> list[SessionContext]:
        """获取所有活跃的 SessionContext。"""
        return list(self._contexts.values())
