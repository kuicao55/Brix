"""SkillCommand -- 将 FileSkill 包装为 Command。"""

from __future__ import annotations

from pathlib import Path

from capability.command.base import (
    Command,
    CommandContext,
    CommandMeta,
    CommandResult,
    CommandResultType,
)
from capability.command.loader import FileSkill


class SkillCommand(Command):
    """将 FileSkill 包装为 Command，实现 prompt 注入。"""

    def __init__(self, skill_dir: Path) -> None:
        self._skill = FileSkill(skill_dir)

    @property
    def meta(self) -> CommandMeta:
        return self._skill.meta

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        """执行 Skill：生成 prompt，返回 PROMPT 结果。"""
        prompt = await self._skill.get_prompt(
            args,
            {"session_id": context.session_id, "skill_dir": self._skill.meta.skill_root},
        )

        return CommandResult(
            type=CommandResultType.PROMPT,
            prompt_text=prompt,
            allowed_tools=self._skill.meta.allowed_tools or None,
            model=self._skill.meta.model,
        )
