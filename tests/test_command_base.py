"""Command 基础类型测试。"""
from __future__ import annotations

import pytest
from capability.command.base import (
    Command,
    CommandContext,
    CommandMeta,
    CommandResult,
    CommandResultType,
    CommandType,
)


def test_command_type_enum():
    """CommandType 应有两个成员。"""
    assert CommandType.SYSTEM.value == "system"
    assert CommandType.SKILL.value == "skill"


def test_command_meta_defaults():
    """CommandMeta 应有合理的默认值。"""
    meta = CommandMeta(name="test", description="desc", type=CommandType.SYSTEM)
    assert meta.when_to_use == ""
    assert meta.user_invocable is True
    assert meta.disable_model_invocation is False


def test_command_result_type_enum():
    """CommandResultType 应有四个成员。"""
    assert CommandResultType.NONE.value == "none"
    assert CommandResultType.QUIT.value == "quit"
    assert CommandResultType.CLEAR.value == "clear"
    assert CommandResultType.PROMPT.value == "prompt"


def test_command_result_defaults():
    """CommandResult 默认值应正确。"""
    result = CommandResult(type=CommandResultType.NONE)
    assert result.prompt_text == ""
    assert result.allowed_tools is None
    assert result.model is None


def test_command_result_prompt():
    """PROMPT 类型的 CommandResult 应携带 prompt_text。"""
    result = CommandResult(
        type=CommandResultType.PROMPT,
        prompt_text="do something",
        allowed_tools=["Bash"],
        model="haiku",
    )
    assert result.prompt_text == "do something"
    assert result.allowed_tools == ["Bash"]
    assert result.model == "haiku"


def test_command_is_abstract():
    """Command 不应被直接实例化。"""
    with pytest.raises(TypeError):
        Command()  # type: ignore


def test_command_context_fields():
    """CommandContext 应包含必要的字段。"""
    ctx = CommandContext()
    assert ctx.session_id == ""
    assert ctx.data_dir == ""
    assert ctx.console is None
    assert ctx.config is not None


class _StubCommand(Command):
    """测试用 Command 子类。"""

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(name="stub", description="stub command", type=CommandType.SYSTEM)

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        return CommandResult(type=CommandResultType.NONE)


@pytest.mark.asyncio
async def test_stub_command_execute():
    """StubCommand 应可正常执行。"""
    cmd = _StubCommand()
    result = await cmd.execute("", CommandContext())
    assert result.type == CommandResultType.NONE
