"""信息查询命令 — /help, /model, /soul, /user, /log。"""

from __future__ import annotations

import sys
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
    """查看或切换主模型。"""

    def __init__(self, config: dict) -> None:
        self._config = config

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="model",
            description="查看或切换主模型 (/model [model_id])",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        # 安全提取 models 列表（防御畸形配置）
        raw_models = self._config.get("models", [])
        models = [m for m in raw_models if isinstance(m, dict)]

        # 有参数：直接切换模型
        if args.strip():
            return self._switch_model(args.strip(), models)

        # 无参数：交互式选择器
        return await self._interactive_select(models)

    def _switch_model(self, model_id: str, models: list[dict]) -> CommandResult:
        """直接切换模型。"""
        valid_ids = {m.get("id") for m in models}
        if model_id not in valid_ids:
            print(f"\n  未知模型: {model_id}")
            print(f"  使用 /model 查看可用模型列表\n")
            return CommandResult(type=CommandResultType.NONE)

        self._config.setdefault("routing", {})["default_model"] = model_id
        print(f"\n  已切换到: {model_id}（本次会话有效）\n")
        return CommandResult(type=CommandResultType.NONE)

    async def _interactive_select(self, models: list[dict]) -> CommandResult:
        """交互式模型选择器（方向键选择，回车确认）。"""
        from cli.paginated_selector import PaginatedSelector

        default_model = self._config.get("routing", {}).get("default_model", "")

        # Server 端没有终端，直接列出可用模型
        if not sys.stdin.isatty():
            print(f"\n  当前模型: {default_model}")
            print(f"  可用模型：\n")
            for m in models:
                mid = m.get("id", "")
                cost = m.get("cost_tier", "?")
                marker = " ← 当前" if mid == default_model else ""
                print(f"    {mid}  [{cost}]{marker}")
            print(f"\n  使用 /model <model_id> 切换\n")
            return CommandResult(type=CommandResultType.NONE)

        def _format(model: dict, idx: int) -> str:
            model_id = model.get("id", "")
            cost = model.get("cost_tier", "?")
            marker = " ← 当前" if model_id == default_model else ""
            return f"{model_id}  [{cost}]{marker}"

        selector = PaginatedSelector(
            items=models,
            format_item=_format,
            page_size=10,
            title=f"切换主模型（当前: {default_model}）",
        )
        selected = await selector.prompt_async()
        if selected is not None:
            model_id = selected.get("id", "")
            self._config.setdefault("routing", {})["default_model"] = model_id
            print(f"\n  已切换到: {model_id}（本次会话有效）\n")

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
