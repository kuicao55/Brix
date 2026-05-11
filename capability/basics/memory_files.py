"""记忆文件操作 — soul.md 和 user.md 的读取。

所有函数接受 MemoryProvider 作为参数，返回结构化数据。
"""

from __future__ import annotations

from memory import MemoryProvider


def load_soul(memory: MemoryProvider) -> str | None:
    """返回 soul.md 内容。不存在返回 None。"""
    if memory.soul_exists():
        return memory.load_soul()
    return None


def load_user(memory: MemoryProvider) -> str | None:
    """返回 user.md 内容。不存在返回 None。"""
    if memory.user_memory_exists():
        return memory.load_user_memory()
    return None
