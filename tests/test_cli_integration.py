"""CLI 集成测试 -- CommandRegistry 集成。"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock

from capability.command.base import (
    Command,
    CommandContext,
    CommandMeta,
    CommandResult,
    CommandResultType,
    CommandType,
)
from capability.command.registry import CommandRegistry


class _StubSystemCmd(Command):
    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(name="stub", description="stub cmd", type=CommandType.SYSTEM)

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        return CommandResult(type=CommandResultType.NONE)


class _StubSkillCmd(Command):
    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="skill-stub",
            description="skill stub",
            type=CommandType.SKILL,
            when_to_use="当需要测试时",
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        return CommandResult(
            type=CommandResultType.PROMPT,
            prompt_text="injected prompt",
            allowed_tools=["Bash"],
            model="haiku",
        )


def test_registry_lookup():
    """CommandRegistry 查找应正常工作。"""
    reg = CommandRegistry()
    reg.register(_StubSystemCmd())
    reg.register(_StubSkillCmd())

    assert reg.get("stub") is not None
    assert reg.get("skill-stub") is not None
    assert reg.get("unknown") is None


def test_skill_listing_injection():
    """Skill 列表文本应只包含 Skill 类型命令。"""
    reg = CommandRegistry()
    reg.register(_StubSystemCmd())
    reg.register(_StubSkillCmd())

    text = reg.get_skill_listing_text()
    lines = text.strip().splitlines()
    # 第一行是标题，后续每行是一个 Skill 条目
    entry_names = [line.split(":")[0].strip().lstrip("- ") for line in lines[1:]]
    assert "/skill-stub" in entry_names
    assert "/stub" not in entry_names  # 系统命令不应出现在 Skill 列表中
    assert "当需要测试时" in text


@pytest.mark.asyncio
async def test_command_dispatch_none():
    """NONE 结果应无特殊行为。"""
    cmd = _StubSystemCmd()
    result = await cmd.execute("", CommandContext())
    assert result.type == CommandResultType.NONE


@pytest.mark.asyncio
async def test_command_dispatch_prompt():
    """PROMPT 结果应携带 prompt_text 和 allowed_tools。"""
    cmd = _StubSkillCmd()
    result = await cmd.execute("some args", CommandContext())
    assert result.type == CommandResultType.PROMPT
    assert result.prompt_text == "injected prompt"
    assert result.allowed_tools == ["Bash"]
    assert result.model == "haiku"
