"""CommandRegistry -- 统一的命令注册表。"""

from __future__ import annotations

from capability.command.base import Command, CommandMeta, CommandType


class CommandRegistry:
    """统一注册表：系统命令 + Skill 命令。"""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        """注册命令，同名覆盖。"""
        self._commands[command.meta.name] = command

    def get(self, name: str) -> Command | None:
        """按名称查找命令。"""
        return self._commands.get(name)

    def list_all(self, include_hidden: bool = False) -> list[CommandMeta]:
        """列出所有命令的元数据。"""
        commands = self._commands.values()
        if not include_hidden:
            commands = [
                c
                for c in commands
                if c.meta.user_invocable or not c.meta.disable_model_invocation
            ]
        return [c.meta for c in commands]

    def get_skill_listing_text(self) -> str:
        """生成供 system prompt 使用的 Skill 列表文本（仅 Skill 类型）。"""
        skills = [
            c.meta
            for c in self._commands.values()
            if c.meta.type == CommandType.SKILL and not c.meta.disable_model_invocation
        ]
        if not skills:
            return ""
        lines = ["The following skills are available for use with the Skill tool:"]
        for meta in skills:
            line = f"- {meta.name}: {meta.description}"
            if meta.when_to_use:
                line += f" ({meta.when_to_use})"
            lines.append(line)
        lines.append("")
        lines.append("Use the Skill tool to execute them when the user's request matches a skill.")
        lines.append("When users reference a \"/<name>\" command, invoke the Skill tool with that name.")
        return "\n".join(lines)
