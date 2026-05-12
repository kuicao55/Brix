"""系统命令测试。"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from capability.command.base import CommandContext, CommandResultType, CommandType
from capability.command.builtin.session import QuitCommand, ClearCommand, HistoryCommand, ResumeCommand
from capability.command.builtin.info import HelpCommand, ModelCommand, SoulCommand, UserCommand, LogCommand


# --- 元数据测试 ---

def test_quit_command_meta():
    cmd = QuitCommand()
    assert cmd.meta.name == "quit"
    assert cmd.meta.type == CommandType.SYSTEM
    assert cmd.meta.user_invocable is True


def test_clear_command_meta():
    cmd = ClearCommand()
    assert cmd.meta.name == "clear"
    assert cmd.meta.type == CommandType.SYSTEM


def test_help_command_meta():
    cmd = HelpCommand(MagicMock())
    assert cmd.meta.name == "help"
    assert cmd.meta.type == CommandType.SYSTEM


def test_model_command_meta():
    cmd = ModelCommand({"routing": {"default_model": "gpt-4"}})
    assert cmd.meta.name == "model"


# --- 执行测试 ---

@pytest.mark.asyncio
async def test_quit_command():
    cmd = QuitCommand()
    # QuitCommand calls sys.exit, so we test meta only
    assert cmd.meta.name == "quit"


@pytest.mark.asyncio
async def test_clear_command():
    cmd = ClearCommand()
    result = await cmd.execute("", CommandContext())
    assert result.type == CommandResultType.CLEAR


@pytest.mark.asyncio
async def test_model_command():
    cmd = ModelCommand({"routing": {"default_model": "gpt-4o-mini"}})
    result = await cmd.execute("", CommandContext())
    assert result.type == CommandResultType.NONE


@pytest.mark.asyncio
async def test_help_command():
    """HelpCommand 应返回 NONE。"""
    from capability.command.registry import CommandRegistry
    from capability.command.base import Command, CommandMeta, CommandResult

    class _Stub(Command):
        @property
        def meta(self):
            return CommandMeta(name="stub", description="stub desc", type=CommandType.SYSTEM)

        async def execute(self, args, context):
            return CommandResult(type=CommandResultType.NONE)

    reg = CommandRegistry()
    reg.register(_Stub())
    cmd = HelpCommand(reg)
    result = await cmd.execute("", CommandContext())
    assert result.type == CommandResultType.NONE


@pytest.mark.asyncio
async def test_history_command_no_sessions():
    """无会话时应返回 NONE。"""
    mock_memory = MagicMock()
    mock_memory.load_sessions_index.return_value = []
    ctx = CommandContext(memory=mock_memory)
    cmd = HistoryCommand()
    result = await cmd.execute("", ctx)
    assert result.type == CommandResultType.NONE


@pytest.mark.asyncio
async def test_soul_command_no_file():
    """无 soul.md 时应返回 NONE。"""
    mock_memory = MagicMock()
    mock_memory.load_memory_file.return_value = None
    ctx = CommandContext(memory=mock_memory)
    cmd = SoulCommand()
    result = await cmd.execute("", ctx)
    assert result.type == CommandResultType.NONE
