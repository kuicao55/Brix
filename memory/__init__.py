"""记忆层 — MemoryProvider Protocol + 工厂函数。"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class MemoryProvider(Protocol):
    """记忆层对外暴露的统一接口。"""

    def load_soul(self) -> str: ...
    def load_user_memory(self) -> str: ...
    def soul_exists(self) -> bool: ...
    def user_memory_exists(self) -> bool: ...
    def create_session(self) -> str: ...
    def add_message(self, role: str, content: str) -> None: ...
    def save_session(self) -> None: ...
    def load_session(self, session_id: str) -> list[dict]: ...
    def resume_session(self, session_id: str) -> list[dict]: ...
    def list_sessions(self) -> list[dict]: ...
    def get_context_messages(self, system_prompt: str) -> list[dict]: ...
    def build_system_prompt(self, session_context: str = "", dynamic_context: str = "") -> str: ...


def create_memory_provider(
    data_dir: str | Path | None = None,
    max_context_tokens: int = 8000,
) -> MemoryProvider:
    """工厂函数 — 创建 BrixMemoryProvider 实例。

    默认 data_dir 为当前工作目录下的 .brix/data，
    避免在已安装环境中写入只读的包目录。
    """
    from memory.provider import BrixMemoryProvider
    if data_dir is None:
        data_dir = Path.cwd() / ".brix" / "data"
    else:
        data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return BrixMemoryProvider(data_dir=data_dir, max_context_tokens=max_context_tokens)
