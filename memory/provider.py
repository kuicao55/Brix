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
    """组合各管理器，实现 MemoryProvider Protocol。

    Session 懒创建：只在发送第一条消息时才创建 session，避免启动时产生空记录。
    """

    def __init__(self, data_dir: Path, max_context_tokens: int = 8000) -> None:
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._soul = SoulManager(data_dir)
        self._user = UserMemoryManager(data_dir)
        self._session_mgr = SessionManager(data_dir)
        self._session_mgr.cleanup_stale_empty_sessions()
        self._current_session_id: str | None = None
        self._storage: MemoryStorage | None = None
        self._has_messages = False  # 当前 session 是否添加过消息
        self._strategy = MemoryStrategy(
            soul_manager=self._soul,
            user_manager=self._user,
            max_tokens=max_context_tokens,
        )

    def _ensure_session(self) -> None:
        """确保当前有活跃 session；没有则懒创建。"""
        if self._current_session_id is None:
            self._current_session_id = self._session_mgr.create_session()
            self._storage = MemoryStorage(self._session_mgr, self._current_session_id)
            self._has_messages = False

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

    def _cleanup_empty_session(self) -> None:
        """如果当前 session 从未添加过消息，从索引中移除。"""
        if self._current_session_id and not self._has_messages:
            self._session_mgr.remove_session_from_index(self._current_session_id)
            self._current_session_id = None
            self._storage = None

    def create_session(self) -> str:
        """创建新会话，返回 UUID。若上一个会话为空则自动清理。"""
        self._cleanup_empty_session()
        self._current_session_id = self._session_mgr.create_session()
        self._storage = MemoryStorage(self._session_mgr, self._current_session_id)
        self._has_messages = False
        return self._current_session_id

    def clear_session(self) -> None:
        """清空当前会话并重置状态，不创建新会话。

        若当前会话有消息，先持久化空消息列表到磁盘。
        下次 add_message 时将懒创建新会话。
        """
        if self._storage is not None and self._has_messages:
            self._storage.clear()
            self._storage.save()
        elif self._current_session_id and not self._has_messages:
            self._session_mgr.remove_session_from_index(self._current_session_id)
        self._current_session_id = None
        self._storage = None
        self._has_messages = False

    def add_message(self, role: str, content: str) -> None:
        """向当前会话添加一条消息。首次调用时懒创建 session。"""
        self._ensure_session()
        self._has_messages = True
        self._storage.add_message(role, content)

    def save_session(self) -> None:
        """持久化当前会话消息到磁盘。无 session 时为空操作。

        若当前 session 从未添加过消息且磁盘上无已有文件，则跳过写入，
        避免产生 message_count=0 的幽灵 session。
        """
        if self._storage is not None:
            # 跳过空 session 的持久化（磁盘上无历史 + 本次无新消息）
            if not self._has_messages and self._storage.is_empty_on_disk():
                return
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
        sessions = self._session_mgr.list_sessions()
        if not any(s["id"] == session_id for s in sessions):
            raise FileNotFoundError(f"Session {session_id} not found")
        self._cleanup_empty_session()
        self._current_session_id = session_id
        self._storage = MemoryStorage(self._session_mgr, session_id)
        self._has_messages = True  # resume 的 session 肯定有消息
        return self._storage.get_history()

    def list_sessions(self) -> list[dict[str, Any]]:
        """返回所有会话索引（最新在前）。"""
        return self._session_mgr.list_sessions()

    def get_context_messages(self, system_prompt: str) -> list[dict[str, Any]]:
        """构建上下文消息列表：system prompt + 策略裁剪后的历史。"""
        system_msg = {"role": "system", "content": system_prompt}
        history = self._storage.get_history() if self._storage is not None else []
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
