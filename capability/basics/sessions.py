"""会话管理功能 — 列出、匹配、恢复、加载会话。

所有函数接受 MemoryProvider 作为参数，返回结构化数据。
"""

from __future__ import annotations

from memory import MemoryProvider


def list_sessions(memory: MemoryProvider) -> list[dict]:
    """返回所有 session 元数据（按更新时间倒序）。

    每个 dict 包含: id, created, updated, message_count, preview
    """
    return memory.list_sessions()


def get_session_by_prefix(memory: MemoryProvider, prefix: str) -> dict | None | str:
    """按 ID 前缀匹配 session。

    返回:
        dict    — 唯一匹配的 session 元数据
        None    — 无匹配
        "ambiguous" — 多个匹配
    """
    sessions = memory.list_sessions()
    matches = [s for s in sessions if s["id"].startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return "ambiguous"
    return None


def resume_session(memory: MemoryProvider, session_id: str) -> list[dict]:
    """恢复 session 并返回完整消息列表。

    每个 dict 包含: role, content, timestamp
    FileNotFoundError — session 文件不存在
    """
    return memory.resume_session(session_id)


def load_session_messages(memory: MemoryProvider, session_id: str) -> list[dict]:
    """加载 session 消息（只读，不切换当前 session）。"""
    return memory.load_session(session_id)
