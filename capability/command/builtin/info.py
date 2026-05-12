"""信息查询命令 — /help, /model, /soul, /user, /log。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from capability.command.base import (
    Command,
    CommandContext,
    CommandMeta,
    CommandResult,
    CommandResultType,
    CommandType,
)

if TYPE_CHECKING:
    from capability.command.registry import CommandRegistry


class HelpCommand(Command):
    """显示所有可用命令。"""

    def __init__(self, registry: CommandRegistry) -> None:
        self._registry = registry

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="help",
            description="显示所有可用命令",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        commands = self._registry.list_all()
        if not commands:
            print("No commands available.")
            return CommandResult(type=CommandResultType.NONE)

        width = max(len(f"/{m.name}") for m in commands) + 2
        print()
        print("  可用命令：")
        print()
        for meta in commands:
            name = f"/{meta.name}"
            print(f"    {name:<{width}} {meta.description}")
        print()
        return CommandResult(type=CommandResultType.NONE)


class ModelCommand(Command):
    """查看当前默认模型。"""

    def __init__(self, config: dict) -> None:
        self._config = config

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="model",
            description="查看当前默认模型",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        default_model = self._config.get("routing", {}).get("default_model", "unknown")
        print(f"Current model: {default_model}")
        return CommandResult(type=CommandResultType.NONE)


class SoulCommand(Command):
    """查看 soul.md 记忆文件。"""

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="soul",
            description="查看 soul.md 记忆文件",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        if not context.memory:
            print("No soul.md yet.")
            return CommandResult(type=CommandResultType.NONE)

        from capability.basics.memory_files import load_soul
        content = load_soul(context.memory)
        if content is not None:
            print(content)
        else:
            print("No soul.md yet. Start a conversation to create it.")
        return CommandResult(type=CommandResultType.NONE)


class UserCommand(Command):
    """查看 user.md 记忆文件。"""

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="user",
            description="查看 user.md 记忆文件",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        if not context.memory:
            print("No user.md yet.")
            return CommandResult(type=CommandResultType.NONE)

        from capability.basics.memory_files import load_user
        content = load_user(context.memory)
        if content is not None:
            print(content)
        else:
            print("No user.md yet. Start a conversation to create it.")
        return CommandResult(type=CommandResultType.NONE)


class LogCommand(Command):
    """交互式日志查看器。"""

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="log",
            description="交互式日志查看器",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        from capability.basics.logs import get_recent_logs

        entries = get_recent_logs(20)
        if not entries:
            print("No logs yet.")
            return CommandResult(type=CommandResultType.NONE)

        for i, entry in enumerate(entries, 1):
            ts = entry.get("ts", "?")
            trace = entry.get("trace", "?")
            preview = entry.get("input", "")[:50].replace("\n", " ")
            ms = entry.get("ms_total", 0)
            error = entry.get("error")
            status = "ERR" if error else "OK"
            print(f"  #{i}  {ts} [{trace}]  {ms}ms  {status}  \"{preview}\"")

        return CommandResult(type=CommandResultType.NONE)
