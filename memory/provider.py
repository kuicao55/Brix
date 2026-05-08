"""BrixMemoryProvider — MemoryProvider Protocol 的具体实现。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from memory.session import SessionManager
from memory.soul import SoulManager
from memory.user import UserMemoryManager
from memory.storage import MemoryStorage
from memory.strategy import MemoryStrategy


class BrixMemoryProvider:
    """组合各管理器，实现 MemoryProvider Protocol。"""

    def __init__(self, data_dir: Path, max_context_tokens: int = 8000) -> None:
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._soul = SoulManager(data_dir)
        self._user = UserMemoryManager(data_dir)
        self._session_mgr = SessionManager(data_dir)
        self._current_session_id = self._session_mgr.create_session()
        self._storage = MemoryStorage(self._session_mgr, self._current_session_id)
        self._strategy = MemoryStrategy(
            soul_manager=self._soul,
            user_manager=self._user,
            max_tokens=max_context_tokens,
        )

    def load_soul(self) -> str:
        """加载 soul.md 内容。"""
        return self._soul.load()

    def load_user_memory(self) -> str:
        """加载 user.md 内容。"""
        return self._user.load()

    def soul_exists(self) -> bool:
        """soul.md 是否存在且非空。"""
        return self._soul.exists()

    def user_memory_exists(self) -> bool:
        """user.md 是否存在且非空。"""
        return self._user.exists()

    def create_session(self) -> str:
        """创建新会话，返回 UUID。"""
        self._current_session_id = self._session_mgr.create_session()
        self._storage = MemoryStorage(self._session_mgr, self._current_session_id)
        return self._current_session_id

    def add_message(self, role: str, content: str) -> None:
        """向当前会话添加一条消息。"""
        self._storage.add_message(role, content)

    def save_session(self) -> None:
        """持久化当前会话消息到磁盘。"""
        self._storage.save()

    def load_session(self, session_id: str) -> list[dict[str, Any]]:
        """加载指定会话的消息列表。"""
        return self._session_mgr.load_session(session_id)

    def resume_session(self, session_id: str) -> list[dict[str, Any]]:
        """恢复指定会话为当前活跃会话。

        加载会话消息、切换 _current_session_id、创建新 MemoryStorage，
        使得后续 add_message / save_session 操作写入该会话。

        若 session_id 不在索引中（既非已有会话也非新建会话），
        抛出 FileNotFoundError。
        """
        # 验证 session_id 是否存在于索引中
        sessions = self._session_mgr.list_sessions()
        if not any(s["id"] == session_id for s in sessions):
            raise FileNotFoundError(f"Session {session_id} not found")
        self._current_session_id = session_id
        self._storage = MemoryStorage(self._session_mgr, session_id)
        return self._storage.get_history()

    def list_sessions(self) -> list[dict[str, Any]]:
        """返回所有会话索引（最新在前）。"""
        return self._session_mgr.list_sessions()

    def get_context_messages(self, system_prompt: str) -> list[dict[str, Any]]:
        """构建上下文消息列表：system prompt + 策略裁剪后的历史。"""
        system_msg = {"role": "system", "content": system_prompt}
        history = self._storage.get_history()
        return self._strategy.get_context_window([system_msg] + history)

    def build_system_prompt(
        self,
        session_context: str = "",
        dynamic_context: str = "",
    ) -> str:
        """构建完整的 system prompt。"""
        return self._strategy.build_system_prompt(
            session_context=session_context,
            dynamic_context=dynamic_context,
        )
