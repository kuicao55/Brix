"""会话管理命令 — /quit, /clear, /resume, /history。"""

from __future__ import annotations

import sys
from typing import Any

from capability.command.base import (
    Command,
    CommandContext,
    CommandMeta,
    CommandResult,
    CommandResultType,
    CommandType,
)


class QuitCommand(Command):
    """退出 REPL。"""

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="quit",
            description="保存会话并退出（也可用 /exit）",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        if context.memory:
            context.memory.save_session()
        print("Goodbye.")
        sys.exit(0)


class ClearCommand(Command):
    """清空当前会话。"""

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="clear",
            description="创建新会话",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        if context.memory:
            context.memory.clear_session()
        print("Session cleared.")
        return CommandResult(type=CommandResultType.CLEAR)


class HistoryCommand(Command):
    """查看当前会话的消息历史。"""

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="history",
            description="查看当前会话的消息历史",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        if not context.memory:
            print("No history yet.")
            return CommandResult(type=CommandResultType.NONE)

        sessions = context.memory.load_sessions_index()
        if not sessions:
            print("No history yet.")
            return CommandResult(type=CommandResultType.NONE)

        sid = sessions[0]["id"]
        msgs = context.memory.load_session(sid)
        if not msgs:
            print("No history yet.")
        else:
            if context.console:
                from cli.display import render_history
                render_history(context.console, msgs)
            else:
                for m in msgs:
                    print(f"  {m.get('role', '?')}: {m.get('content', '')[:80]}")
        return CommandResult(type=CommandResultType.NONE)


class ResumeCommand(Command):
    """恢复历史会话。"""

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="resume",
            description="恢复历史会话（交互式选择或按 ID 前缀）",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        if not context.memory:
            print("No sessions yet.")
            return CommandResult(type=CommandResultType.NONE)

        sessions = context.memory.load_sessions_index()
        if not sessions:
            print("No sessions yet.")
            return CommandResult(type=CommandResultType.NONE)

        # 简化实现：打印会话列表
        for i, s in enumerate(sessions[:10], 1):
            sid = s.get("id", "?")[:8]
            count = s.get("message_count", 0)
            print(f"  {i}. {sid} ({count} msgs)")

        return CommandResult(type=CommandResultType.NONE)
