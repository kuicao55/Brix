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

        sessions = context.memory.list_sessions()
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

        sessions = context.memory.list_sessions()
        if not sessions:
            print("No sessions yet.")
            return CommandResult(type=CommandResultType.NONE)

        # 带 ID 前缀时尝试直接匹配
        if args.strip():
            prefix = args.strip()
            matches = [s for s in sessions if s["id"].startswith(prefix)]
            if len(matches) == 1:
                self._resume_and_render(context, matches[0]["id"])
                return CommandResult(type=CommandResultType.NONE)
            if len(matches) > 1:
                print(f"Ambiguous prefix, {len(matches)} matches. Opening selector...")

        # 交互式分页选择器
        def format_session(s: dict, idx: int) -> str:
            sid = s.get("id", "?")[:8]
            count = s.get("message_count", 0)
            updated = s.get("updated", "")[:10]  # YYYY-MM-DD
            preview = s.get("preview", "")[:40].replace("\n", " ")
            return f"{sid}  {count:>3} msgs  {updated}  {preview}"

        from cli.paginated_selector import PaginatedSelector

        selector = PaginatedSelector(
            items=sessions,
            format_item=format_session,
            page_size=10,
            title="选择要恢复的会话",
        )
        selected = await selector.prompt_async()
        if selected is not None:
            self._resume_and_render(context, selected["id"])

        return CommandResult(type=CommandResultType.NONE)

    @staticmethod
    def _resume_and_render(context: CommandContext, session_id: str) -> None:
        """恢复会话并用完整聊天 UI 渲染历史。"""
        try:
            msgs = context.memory.resume_session(session_id)
            if context.console:
                context.console.print(
                    f"[dim]Resumed session {session_id[:8]}... ({len(msgs)} messages)[/]"
                )
                if msgs:
                    from cli.display import render_history

                    context.console.print()
                    render_history(context.console, msgs)
            else:
                print(f"Resumed session {session_id[:8]}... ({len(msgs)} messages)")
        except FileNotFoundError:
            print(f"Session not found: {session_id[:8]}...")
