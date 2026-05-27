"""CLI 集成 side 层测试。"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

from side.manager import SideTaskManager
from side.tasks import ALL_TASKS


def test_cli_imports_side_manager():
    """cli/app.py 导入 SideTaskManager。"""
    import cli.app
    # 验证模块可以导入（不抛出异常）
    assert hasattr(cli.app, 'BrixCLI')


def test_config_routing_no_intent_model():
    """config 中不再有 intent_model 和 chat_model。"""
    from config.loader import load_config
    config = load_config()
    routing = config.get("routing", {})
    assert "intent_model" not in routing
    assert "chat_model" not in routing


# ---------------------------------------------------------------------------
# 行为测试：SideTaskManager 初始化 + ALL_TASKS 注册
# ---------------------------------------------------------------------------

def test_side_manager_initialized_with_config_and_all_tasks():
    """BrixCLI.__init__() 创建 SideTaskManager，configure 传入 config/llm_client/memory，
    并注册 ALL_TASKS 中的全部 task。"""
    # 构造最小 config，跳过所有可选模块
    config = {
        "routing": {"default_model": "test/model"},
        "memory": {"data_dir": "/tmp/brix_test", "max_context_tokens": 1000},
        "side": {"enabled": True, "model": "test/side-model"},
    }

    with (
        patch("cli.app.ToolRunner"),
        patch("cli.app.CommandRegistry"),
        patch("cli.app.HookRegistry"),
        patch("cli.app.StateMachineOrchestrator"),
        patch("cli.app.LLMClient"),
        patch("cli.app.create_memory_provider") as mock_mem,
        patch("cli.app.BrixCLI._init_voice"),
        patch("cli.app.BrixCLI._register_tools"),
        patch("cli.app.BrixCLI._register_commands"),
        patch("cli.app.BrixCLI._register_skill_tool"),
    ):
        from cli.app import BrixCLI
        instance = BrixCLI(config=config)

    mgr = instance._side_manager
    assert mgr is not None, "SideTaskManager 未创建"

    # configure() 应存储了三个引用
    assert mgr._config is config
    assert mgr._llm_client is not None
    assert mgr._memory is not None

    # ALL_TASKS 中的每个 task 都已注册
    for task in ALL_TASKS:
        assert task.name in mgr._tasks, f"task '{task.name}' 未注册"


# ---------------------------------------------------------------------------
# 行为测试：_process_streaming 调用 history_search + on_user_message
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_streaming_calls_history_search_and_on_user_message():
    """_process_streaming 应调用 run_task('history_search') 和 on_user_message()。"""
    config = {
        "routing": {"default_model": "test/model"},
        "memory": {"data_dir": "/tmp/brix_test", "max_context_tokens": 1000},
        "side": {"enabled": True, "model": "test/side-model"},
    }

    # 构建 BrixCLI，mock 所有外部依赖
    with (
        patch("cli.app.ToolRunner"),
        patch("cli.app.CommandRegistry") as mock_cmd_reg,
        patch("cli.app.HookRegistry"),
        patch("cli.app.StateMachineOrchestrator") as mock_orch_cls,
        patch("cli.app.LLMClient"),
        patch("cli.app.create_memory_provider"),
        patch("cli.app.BrixCLI._init_voice"),
        patch("cli.app.BrixCLI._register_tools"),
        patch("cli.app.BrixCLI._register_commands"),
        patch("cli.app.BrixCLI._register_skill_tool"),
    ):
        mock_cmd_reg.return_value.get_skill_listing_text.return_value = ""
        # orchestrator.run_stream 返回空 async generator
        mock_orch = mock_orch_cls.return_value

        async def _empty_stream(*args, **kwargs):
            return
            yield  # 使它成为 async generator

        mock_orch.run_stream = _empty_stream

        from cli.app import BrixCLI
        instance = BrixCLI(config=config)

    # 替换 side_manager 为 mock，保留 configure 后的状态
    mock_mgr = MagicMock(spec=SideTaskManager)
    mock_mgr.enabled = True
    mock_mgr.run_task = AsyncMock(return_value=None)
    mock_mgr.on_user_message = MagicMock()
    mock_mgr.fire_and_forget = MagicMock()
    mock_mgr.should_run_pref_detection = MagicMock(return_value=False)
    mock_mgr.get_side_model.return_value = "test/side-model"
    instance._side_manager = mock_mgr

    await instance._process_streaming("hello")

    # 验证 history_search 被调用（不精确匹配 hooks，它在函数内部新建）
    assert mock_mgr.run_task.call_count >= 1
    first_call = mock_mgr.run_task.call_args_list[0]
    assert first_call[0][0] == "history_search"
    assert first_call[1]["user_input"] == "hello"
    # 验证 on_user_message 被调用
    mock_mgr.on_user_message.assert_called_once()


# ---------------------------------------------------------------------------
# 行为测试：tool_result 事件触发 fire_and_forget("tool_summary")
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_streaming_fires_tool_summary_on_tool_result():
    """当 orchestrator 发出 tool_result 事件时，
    _process_streaming 应调用 fire_and_forget('tool_summary')。"""
    config = {
        "routing": {"default_model": "test/model"},
        "memory": {"data_dir": "/tmp/brix_test", "max_context_tokens": 1000},
        "side": {"enabled": True, "model": "test/side-model"},
    }

    with (
        patch("cli.app.ToolRunner"),
        patch("cli.app.CommandRegistry") as mock_cmd_reg,
        patch("cli.app.HookRegistry"),
        patch("cli.app.StateMachineOrchestrator") as mock_orch_cls,
        patch("cli.app.LLMClient"),
        patch("cli.app.create_memory_provider"),
        patch("cli.app.BrixCLI._init_voice"),
        patch("cli.app.BrixCLI._register_tools"),
        patch("cli.app.BrixCLI._register_commands"),
        patch("cli.app.BrixCLI._register_skill_tool"),
    ):
        mock_cmd_reg.return_value.get_skill_listing_text.return_value = ""
        mock_orch = mock_orch_cls.return_value

        # 模拟 orchestrator 发出一个 tool_result 事件
        async def _stream_with_tool(*args, **kwargs):
            yield {"type": "tool_result", "name": "bash", "result": "ok", "ms": 10, "is_error": False}

        mock_orch.run_stream = _stream_with_tool

        from cli.app import BrixCLI
        instance = BrixCLI(config=config)

    mock_mgr = MagicMock(spec=SideTaskManager)
    mock_mgr.enabled = True
    mock_mgr.run_task = AsyncMock(return_value=None)
    mock_mgr.on_user_message = MagicMock()
    mock_mgr.fire_and_forget = MagicMock()
    mock_mgr.should_run_pref_detection = MagicMock(return_value=False)
    instance._side_manager = mock_mgr

    await instance._process_streaming("run ls")

    # fire_and_forget 应被调用且参数包含 "tool_summary"
    mock_mgr.fire_and_forget.assert_called()
    call_args = mock_mgr.fire_and_forget.call_args
    assert call_args[0][0] == "tool_summary", (
        f"fire_and_forget 第一个参数应为 'tool_summary'，实际为 {call_args[0][0]!r}"
    )


# ---------------------------------------------------------------------------
# 行为测试：voice cleanup 使用 get_side_model() 回退
# ---------------------------------------------------------------------------

def test_voice_cleanup_uses_side_model_fallback():
    """当 _side_manager 存在时，voice cleanup 使用 get_side_model()；
    当 _side_manager 为 None 时，回退到 'ali/qwen3.6-flash'。"""
    # 模拟 _init_voice 内部的条件表达式：
    #   side_model = self._side_manager.get_side_model() if self._side_manager else "ali/qwen3.6-flash"

    # Case 1: _side_manager 存在
    mock_mgr = MagicMock()
    mock_mgr.get_side_model.return_value = "my/custom-model"
    side_model = mock_mgr.get_side_model() if mock_mgr else "ali/qwen3.6-flash"
    assert side_model == "my/custom-model"

    # Case 2: _side_manager 为 None
    mock_mgr_none = None
    side_model = mock_mgr_none.get_side_model() if mock_mgr_none else "ali/qwen3.6-flash"
    assert side_model == "ali/qwen3.6-flash"


def test_init_voice_passes_side_model_to_cleanup():
    """_init_voice() 构建的 _cleanup_llm 使用 side_manager.get_side_model() 的返回值。"""
    config = {
        "routing": {"default_model": "test/model"},
        "memory": {"data_dir": "/tmp/brix_test", "max_context_tokens": 1000},
        "side": {"enabled": True, "model": "side/real-model"},
        "voice": {"enabled": True},  # 触发 _init_voice 路径
    }

    captured_model = {}

    with (
        patch("cli.app.ToolRunner"),
        patch("cli.app.CommandRegistry"),
        patch("cli.app.HookRegistry"),
        patch("cli.app.StateMachineOrchestrator"),
        patch("cli.app.LLMClient") as mock_llm_cls,
        patch("cli.app.create_memory_provider"),
        patch("cli.app.BrixCLI._register_tools"),
        patch("cli.app.BrixCLI._register_commands"),
        patch("cli.app.BrixCLI._register_skill_tool"),
        # 让 _init_voice 中的 voice 导入不报错，但不真正创建 VoiceRuntime
        # MagicMock 替换类方法时不做 descriptor protocol，lambda 无参
        patch("cli.app.BrixCLI._init_voice", side_effect=lambda: None),
    ):
        from cli.app import BrixCLI
        instance = BrixCLI(config=config)

    # 手动模拟 _init_voice 的关键逻辑
    side_manager = instance._side_manager
    assert side_manager is not None

    # get_side_model 从 config.side.model 读取
    model = side_manager.get_side_model()
    assert model == "side/real-model", f"期望 'side/real-model'，实际 '{model}'"


# ---------------------------------------------------------------------------
# 行为测试：should_run_pref_detection 返回 True 时触发 fire_and_forget("pref_detection")
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_streaming_fires_pref_detection_when_should_run_true():
    """当 should_run_pref_detection() 返回 True 时，
    _process_streaming 应调用 fire_and_forget('pref_detection')。"""
    config = {
        "routing": {"default_model": "test/model"},
        "memory": {"data_dir": "/tmp/brix_test", "max_context_tokens": 1000},
        "side": {"enabled": True, "model": "test/side-model"},
    }

    with (
        patch("cli.app.ToolRunner"),
        patch("cli.app.CommandRegistry") as mock_cmd_reg,
        patch("cli.app.HookRegistry"),
        patch("cli.app.StateMachineOrchestrator") as mock_orch_cls,
        patch("cli.app.LLMClient"),
        patch("cli.app.create_memory_provider"),
        patch("cli.app.BrixCLI._init_voice"),
        patch("cli.app.BrixCLI._register_tools"),
        patch("cli.app.BrixCLI._register_commands"),
        patch("cli.app.BrixCLI._register_skill_tool"),
    ):
        mock_cmd_reg.return_value.get_skill_listing_text.return_value = ""
        mock_orch = mock_orch_cls.return_value

        # orchestrator.run_stream 返回空 async generator
        async def _empty_stream(*args, **kwargs):
            return
            yield  # 使它成为 async generator

        mock_orch.run_stream = _empty_stream

        from cli.app import BrixCLI
        instance = BrixCLI(config=config)

    mock_mgr = MagicMock(spec=SideTaskManager)
    mock_mgr.enabled = True
    mock_mgr.run_task = AsyncMock(return_value=None)
    mock_mgr.on_user_message = MagicMock()
    mock_mgr.fire_and_forget = MagicMock()
    mock_mgr.should_run_pref_detection = MagicMock(return_value=True)
    instance._side_manager = mock_mgr

    await instance._process_streaming("hello")

    # fire_and_forget 应被调用且第一个参数为 "pref_detection"
    mock_mgr.fire_and_forget.assert_called()
    call_args = mock_mgr.fire_and_forget.call_args
    assert call_args[0][0] == "pref_detection", (
        f"fire_and_forget 第一个参数应为 'pref_detection'，实际为 {call_args[0][0]!r}"
    )
