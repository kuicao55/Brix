"""SkillTool 测试。"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from capability.command.base import (
    Command,
    CommandContext,
    CommandMeta,
    CommandResult,
    CommandResultType,
    CommandType,
)
from capability.command.registry import CommandRegistry
from capability.tools.skill_tool import SkillTool, SKILL_PROMPT_PREFIX


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _StubSkill(Command):
    """可配置的 stub skill。"""

    def __init__(
        self,
        name: str = "test-skill",
        prompt: str = "skill prompt",
        allowed_tools: list[str] | None = None,
        model: str | None = None,
    ):
        self._name = name
        self._prompt = prompt
        self._allowed_tools = allowed_tools
        self._model = model

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name=self._name,
            description=f"stub {self._name}",
            type=CommandType.SKILL,
            when_to_use="测试时",
            allowed_tools=self._allowed_tools or [],
            model=self._model,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        return CommandResult(
            type=CommandResultType.PROMPT,
            prompt_text=self._prompt,
            allowed_tools=self._allowed_tools,
            model=self._model,
        )


def _make_registry(*skills: Command) -> CommandRegistry:
    reg = CommandRegistry()
    for s in skills:
        reg.register(s)
    return reg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_returns_prompt_with_prefix():
    """PROMPT 类型 skill 应返回带 SKILL_PROMPT_PREFIX 前缀的内容。"""
    skill = _StubSkill(prompt="do something")
    tool = SkillTool(registry=_make_registry(skill))
    result = await tool.execute(skill="test-skill")
    assert result.startswith(SKILL_PROMPT_PREFIX)
    assert "do something" in result


@pytest.mark.asyncio
async def test_execute_with_args():
    """args 应正确传递到 skill.execute。"""
    captured_args: list[str] = []

    class _CaptureSkill(Command):
        @property
        def meta(self) -> CommandMeta:
            return CommandMeta(name="cap", description="cap", type=CommandType.SKILL)

        async def execute(self, args: str, context: CommandContext) -> CommandResult:
            captured_args.append(args)
            return CommandResult(type=CommandResultType.PROMPT, prompt_text=f"args={args}")

    tool = SkillTool(registry=_make_registry(_CaptureSkill()))
    result = await tool.execute(skill="cap", args="-m 'fix bug'")
    assert captured_args == ["-m 'fix bug'"]
    assert result == SKILL_PROMPT_PREFIX + "args=-m 'fix bug'"


@pytest.mark.asyncio
async def test_execute_unknown_skill():
    """调用未注册 skill 应返回错误信息。"""
    tool = SkillTool(registry=CommandRegistry())
    result = await tool.execute(skill="nonexistent")
    assert "Error" in result or "error" in result
    assert "nonexistent" in result


@pytest.mark.asyncio
async def test_input_schema():
    """input_schema 应包含 skill（required）和 args（optional）。"""
    tool = SkillTool(registry=CommandRegistry())
    schema = tool.input_schema
    assert schema["type"] == "object"
    assert "skill" in schema["properties"]
    assert "args" in schema["properties"]
    assert "skill" in schema["required"]
    assert "args" not in schema["required"]


@pytest.mark.asyncio
async def test_name_and_description():
    """name 和 description 应有合理值。"""
    tool = SkillTool(registry=CommandRegistry())
    assert isinstance(tool.name, str) and len(tool.name) > 0
    assert isinstance(tool.description, str) and len(tool.description) > 0


@pytest.mark.asyncio
async def test_skill_prompt_prefix_constant():
    """SKILL_PROMPT_PREFIX 应有定义且非空。"""
    assert SKILL_PROMPT_PREFIX
    assert isinstance(SKILL_PROMPT_PREFIX, str)
