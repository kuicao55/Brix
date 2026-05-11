"""Agent 基础功能模块 — 会话、记忆文件、日志、命令注册表。

所有函数返回结构化数据，不直接 print，供任意 UI 层调用。
"""

from capability.basics.sessions import (
    get_session_by_prefix,
    list_sessions,
    load_session_messages,
    resume_session,
)
from capability.basics.memory_files import load_soul, load_user
from capability.basics.logs import get_log_detail, get_recent_logs
from capability.basics.commands import COMMANDS, get_command_list

__all__ = [
    "list_sessions",
    "get_session_by_prefix",
    "resume_session",
    "load_session_messages",
    "load_soul",
    "load_user",
    "get_recent_logs",
    "get_log_detail",
    "COMMANDS",
    "get_command_list",
]
