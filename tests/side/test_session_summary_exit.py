"""SessionSummaryTask 退出路径集成测试。"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from side.manager import SideTaskManager
from side.tasks.session_summary import SessionSummaryTask


def _make_brix_cli_mock():
    """创建 BrixCLI 的最小 mock，用于测试退出路径。"""
    config = {
        "routing": {"default_model": "test/model"},
        "memory": {"data_dir": "/tmp/brix_test", "max_context_tokens": 1000},
        "side": {
            "enabled": True,
            "model": "test/side-model",
            "tasks": {"session_summary": {"enabled": True}},
        },
    }

    mock_memory = MagicMock()
    mock_memory.current_session_id = "test-session-001"
    mock_memory.load_session = MagicMock(return_value=[
        {"role": "user", "content": "帮我写代码"},
        {"role": "assistant", "content": "好的"},
    ])
    mock_memory.short_term = MagicMock()
    mock_memory.short_term.get_by_session = MagicMock(return_value=[])
    mock_memory.list_sessions = MagicMock(return_value=[
        {"id": "test-session-001", "created": "2025-06-05T10:00:00+00:00"},
    ])

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "用户在开发 Python 项目。"
    mock_llm.chat = AsyncMock(return_value=mock_response)

    return config, mock_memory, mock_llm


@pytest.mark.asyncio
async def test_save_session_summary_calls_manager():
    """_save_session_summary 调用 side_manager.generate_session_summary()。"""
    with (
        patch("cli.app.ToolRunner"),
        patch("cli.app.CommandRegistry"),
        patch("cli.app.HookRegistry"),
        patch("cli.app.StateMachineOrchestrator"),
        patch("cli.app.LLMClient"),
        patch("cli.app.create_memory_provider"),
        patch("cli.app.BrixCLI._init_voice"),
        patch("cli.app.BrixCLI._register_tools"),
        patch("cli.app.BrixCLI._register_commands"),
        patch("cli.app.BrixCLI._register_skill_tool"),
    ):
        from cli.app import BrixCLI
        config, mock_memory, mock_llm = _make_brix_cli_mock()
        instance = BrixCLI(config=config)

    # 替换 side_manager 为 mock
    mock_mgr = MagicMock(spec=SideTaskManager)
    mock_mgr.enabled = True
    mock_mgr.generate_session_summary = AsyncMock(return_value="摘要内容")
    instance._side_manager = mock_mgr
    instance._memory = mock_memory

    await instance._save_session_summary()
    mock_mgr.generate_session_summary.assert_called_once()


@pytest.mark.asyncio
async def test_save_session_summary_no_manager():
    """无 side_manager 时 _save_session_summary 不崩溃。"""
    with (
        patch("cli.app.ToolRunner"),
        patch("cli.app.CommandRegistry"),
        patch("cli.app.HookRegistry"),
        patch("cli.app.StateMachineOrchestrator"),
        patch("cli.app.LLMClient"),
        patch("cli.app.create_memory_provider"),
        patch("cli.app.BrixCLI._init_voice"),
        patch("cli.app.BrixCLI._register_tools"),
        patch("cli.app.BrixCLI._register_commands"),
        patch("cli.app.BrixCLI._register_skill_tool"),
    ):
        from cli.app import BrixCLI
        config, mock_memory, mock_llm = _make_brix_cli_mock()
        instance = BrixCLI(config=config)

    instance._side_manager = None
    # 不应崩溃
    await instance._save_session_summary()


@pytest.mark.asyncio
async def test_save_session_summary_side_disabled():
    """side 层未启用时 _save_session_summary 不调用 manager。"""
    with (
        patch("cli.app.ToolRunner"),
        patch("cli.app.CommandRegistry"),
        patch("cli.app.HookRegistry"),
        patch("cli.app.StateMachineOrchestrator"),
        patch("cli.app.LLMClient"),
        patch("cli.app.create_memory_provider"),
        patch("cli.app.BrixCLI._init_voice"),
        patch("cli.app.BrixCLI._register_tools"),
        patch("cli.app.BrixCLI._register_commands"),
        patch("cli.app.BrixCLI._register_skill_tool"),
    ):
        from cli.app import BrixCLI
        config, mock_memory, mock_llm = _make_brix_cli_mock()
        instance = BrixCLI(config=config)

    mock_mgr = MagicMock(spec=SideTaskManager)
    mock_mgr.enabled = False
    mock_mgr.generate_session_summary = AsyncMock(return_value="摘要")
    instance._side_manager = mock_mgr

    await instance._save_session_summary()
    mock_mgr.generate_session_summary.assert_not_called()


@pytest.mark.asyncio
async def test_handle_command_triggers_summary_for_clear():
    """/clear 命令触发会话摘要保存。"""
    with (
        patch("cli.app.ToolRunner"),
        patch("cli.app.CommandRegistry") as mock_cmd_reg,
        patch("cli.app.HookRegistry"),
        patch("cli.app.StateMachineOrchestrator"),
        patch("cli.app.LLMClient"),
        patch("cli.app.create_memory_provider"),
        patch("cli.app.BrixCLI._init_voice"),
        patch("cli.app.BrixCLI._register_tools"),
        patch("cli.app.BrixCLI._register_commands"),
        patch("cli.app.BrixCLI._register_skill_tool"),
    ):
        from cli.app import BrixCLI
        from capability.command.base import CommandResult, CommandResultType
        config, mock_memory, mock_llm = _make_brix_cli_mock()
        instance = BrixCLI(config=config)

    # mock _save_session_summary
    instance._save_session_summary = AsyncMock()

    # mock clear command
    mock_cmd = MagicMock()
    mock_cmd.execute = AsyncMock(return_value=CommandResult(type=CommandResultType.CLEAR))
    mock_cmd_reg.return_value.get.return_value = mock_cmd

    instance._memory = mock_memory
    result = await instance._handle_command("/clear")

    # _save_session_summary 应被调用
    instance._save_session_summary.assert_called_once()


@pytest.mark.asyncio
async def test_handle_command_triggers_summary_for_quit():
    """/quit 命令触发会话摘要保存。"""
    with (
        patch("cli.app.ToolRunner"),
        patch("cli.app.CommandRegistry") as mock_cmd_reg,
        patch("cli.app.HookRegistry"),
        patch("cli.app.StateMachineOrchestrator"),
        patch("cli.app.LLMClient"),
        patch("cli.app.create_memory_provider"),
        patch("cli.app.BrixCLI._init_voice"),
        patch("cli.app.BrixCLI._register_tools"),
        patch("cli.app.BrixCLI._register_commands"),
        patch("cli.app.BrixCLI._register_skill_tool"),
    ):
        from cli.app import BrixCLI
        from capability.command.base import CommandResult, CommandResultType
        config, mock_memory, mock_llm = _make_brix_cli_mock()
        instance = BrixCLI(config=config)

    # mock _save_session_summary
    instance._save_session_summary = AsyncMock()

    # mock quit command
    mock_cmd = MagicMock()
    mock_cmd.execute = AsyncMock(return_value=CommandResult(type=CommandResultType.QUIT))
    mock_cmd_reg.return_value.get.return_value = mock_cmd

    instance._memory = mock_memory
    result = await instance._handle_command("/quit")

    # _save_session_summary 应被调用
    instance._save_session_summary.assert_called_once()


@pytest.mark.asyncio
async def test_handle_command_no_summary_for_other_commands():
    """非 /clear、/quit 命令不触发摘要保存。"""
    with (
        patch("cli.app.ToolRunner"),
        patch("cli.app.CommandRegistry") as mock_cmd_reg,
        patch("cli.app.HookRegistry"),
        patch("cli.app.StateMachineOrchestrator"),
        patch("cli.app.LLMClient"),
        patch("cli.app.create_memory_provider"),
        patch("cli.app.BrixCLI._init_voice"),
        patch("cli.app.BrixCLI._register_tools"),
        patch("cli.app.BrixCLI._register_commands"),
        patch("cli.app.BrixCLI._register_skill_tool"),
    ):
        from cli.app import BrixCLI
        from capability.command.base import CommandResult, CommandResultType
        config, mock_memory, mock_llm = _make_brix_cli_mock()
        instance = BrixCLI(config=config)

    # mock _save_session_summary
    instance._save_session_summary = AsyncMock()

    # mock help command
    mock_cmd = MagicMock()
    mock_cmd.execute = AsyncMock(return_value=CommandResult(type=CommandResultType.NONE))
    mock_cmd_reg.return_value.get.return_value = mock_cmd

    instance._memory = mock_memory
    result = await instance._handle_command("/help")

    # _save_session_summary 不应被调用
    instance._save_session_summary.assert_not_called()


@pytest.mark.asyncio
async def test_manager_check_previous_session_summary():
    """check_previous_session_summary 检查上一个 session 并生成摘要。"""
    mgr = SideTaskManager()
    mock_memory = MagicMock()
    mock_memory.current_session_id = "current-session"
    mock_memory.list_sessions = MagicMock(return_value=[
        {"id": "current-session", "created": "2025-06-06T10:00:00+00:00"},
        {"id": "prev-session", "created": "2025-06-05T10:00:00+00:00"},
    ])
    mock_memory.short_term = MagicMock()
    mock_memory.short_term.get_by_session = MagicMock(return_value=[])
    mock_memory.load_session = MagicMock(return_value=[
        {"role": "user", "content": "之前的对话"},
    ])

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "之前的摘要。"
    mock_llm.chat = AsyncMock(return_value=mock_response)

    mgr.configure(
        config={"side": {"enabled": True, "model": "test-model",
                         "tasks": {"session_summary": {"enabled": True}}}},
        llm_client=mock_llm,
        memory=mock_memory,
    )
    mgr.register(SessionSummaryTask())

    result = await mgr.check_previous_session_summary()
    assert result is not None
    # 应该调用了 load_session 来加载上一个 session
    mock_memory.load_session.assert_called_once_with("prev-session")


@pytest.mark.asyncio
async def test_manager_check_previous_session_summary_already_exists():
    """上一个 session 已有摘要时跳过生成。"""
    mgr = SideTaskManager()
    mock_memory = MagicMock()
    mock_memory.current_session_id = "current-session"
    mock_memory.list_sessions = MagicMock(return_value=[
        {"id": "current-session", "created": "2025-06-06T10:00:00+00:00"},
        {"id": "prev-session", "created": "2025-06-05T10:00:00+00:00"},
    ])
    mock_memory.short_term = MagicMock()
    # 上一个 session 已有 event 类型的 item
    mock_memory.short_term.get_by_session = MagicMock(return_value=[
        {"type": "event", "source": "side_summary", "content": "已有摘要"},
    ])

    mgr.configure(
        config={"side": {"enabled": True, "model": "test-model",
                         "tasks": {"session_summary": {"enabled": True}}}},
        llm_client=MagicMock(),
        memory=mock_memory,
    )
    mgr.register(SessionSummaryTask())

    result = await mgr.check_previous_session_summary()
    assert result is None
    # 不应调用 load_session（已有摘要，跳过）
    mock_memory.load_session.assert_not_called()
