"""命令注册表 — 所有可用命令的名称和描述。

供 /help 命令和其他 UI 的帮助系统使用。
"""

from __future__ import annotations

COMMANDS: list[tuple[str, str]] = [
    ("/help",        "显示所有可用命令"),
    ("/quit",        "保存会话并退出（也可用 /exit）"),
    ("/clear",       "创建新会话"),
    ("/model",       "查看当前默认模型"),
    ("/history",     "查看当前会话的消息历史"),
    ("/resume [id]", "恢复历史会话（交互式选择或按 ID 前缀）"),
    ("/soul",        "查看 soul.md 记忆文件"),
    ("/user",        "查看 user.md 记忆文件"),
    ("/log",         "交互式日志查看器"),
]


def get_command_list() -> list[tuple[str, str]]:
    """返回所有命令的 (名称, 描述) 列表。"""
    return list(COMMANDS)
