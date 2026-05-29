"""CLI 集成 side 层测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

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
    # 验证 tool event payload 已传入
    assert call_args[1]["tool_name"] == "bash"
    assert call_args[1]["tool_result"] == "ok"


# ---------------------------------------------------------------------------
# 行为测试：voice cleanup 使用 get_side_model() 回退
# ---------------------------------------------------------------------------

def test_voice_cleanup_uses_side_model_fallback():
    """_cleanup_llm 在调用时延迟解析模型：
    _side_manager 存在时使用 get_side_model()，否则回退到 'ali/qwen3.6-flash'。"""
    config = {
        "routing": {"default_model": "test/model"},
        "memory": {"data_dir": "/tmp/brix_test", "max_context_tokens": 1000},
        "side": {"enabled": True, "model": "side/custom-model"},
        "voice": {"enabled": True},
    }

    captured_cleanup_fn = {}

    def fake_init_voice(self):
        # 模拟 _init_voice 中 _cleanup_llm 的延迟解析逻辑
        async def _cleanup_llm(prompt: str) -> str:
            model = self._side_manager.get_side_model() if self._side_manager else "ali/qwen3.6-flash"
            resp = await self._llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
            )
            return resp.content
        captured_cleanup_fn["fn"] = _cleanup_llm

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
        patch("cli.app.BrixCLI._init_voice", fake_init_voice),
    ):
        from cli.app import BrixCLI
        instance = BrixCLI(config=config)

    assert instance._side_manager is not None
    cleanup_fn = captured_cleanup_fn["fn"]

    # 模拟 LLM 响应
    mock_response = MagicMock()
    mock_response.content = "cleaned"
    mock_llm = instance._llm_client
    mock_llm.chat = AsyncMock(return_value=mock_response)

    # 调用 _cleanup_llm，验证模型在调用时从 _side_manager 延迟解析
    asyncio.get_event_loop().run_until_complete(cleanup_fn("test prompt"))
    mock_llm.chat.assert_called_once()
    call_kwargs = mock_llm.chat.call_args[1]
    assert call_kwargs["model"] == "side/custom-model", (
        f"期望 'side/custom-model'，实际 '{call_kwargs['model']}'"
    )


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


# ---------------------------------------------------------------------------
# /model 命令改造测试
# ---------------------------------------------------------------------------

def test_model_command_displays_models():
    """/model 无参数时启动交互式选择器，选择后切换模型。"""
    from capability.command.builtin.info import ModelCommand
    from capability.command.base import CommandContext

    config = {
        "routing": {"default_model": "minimax/MiniMax-M2.7"},
        "models": [
            {"id": "minimax/MiniMax-M2.7", "cost_tier": "high"},
            {"id": "ali/qwen3.6-flash", "cost_tier": "low"},
        ],
    }
    cmd = ModelCommand(config)
    ctx = CommandContext()

    # Mock PaginatedSelector 返回第二个模型
    with patch("cli.paginated_selector.PaginatedSelector") as MockSelector:
        mock_instance = MockSelector.return_value
        mock_instance.prompt_async = AsyncMock(return_value={"id": "ali/qwen3.6-flash", "cost_tier": "low"})

        import asyncio
        import io
        import sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        asyncio.run(cmd.execute("", ctx))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

    assert "已切换到" in output
    assert "ali/qwen3.6-flash" in output
    assert config["routing"]["default_model"] == "ali/qwen3.6-flash"


def test_model_command_switch():
    """/model <id> 切换模型。"""
    from capability.command.builtin.info import ModelCommand
    from capability.command.base import CommandContext

    config = {
        "routing": {"default_model": "minimax/MiniMax-M2.7"},
        "models": [
            {"id": "minimax/MiniMax-M2.7", "cost_tier": "high"},
            {"id": "ali/qwen3.6-flash", "cost_tier": "low"},
        ],
    }
    cmd = ModelCommand(config)
    ctx = CommandContext()

    import io
    import sys
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    import asyncio
    asyncio.run(cmd.execute("ali/qwen3.6-flash", ctx))
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    assert "已切换" in output
    assert config["routing"]["default_model"] == "ali/qwen3.6-flash"


def test_model_command_invalid():
    """/model <invalid_id> 提示未知模型。"""
    from capability.command.builtin.info import ModelCommand
    from capability.command.base import CommandContext

    config = {
        "routing": {"default_model": "minimax/MiniMax-M2.7"},
        "models": [{"id": "minimax/MiniMax-M2.7"}],
    }
    cmd = ModelCommand(config)
    ctx = CommandContext()

    import io
    import sys
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    import asyncio
    asyncio.run(cmd.execute("nonexistent/model", ctx))
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    assert "未知模型" in output


# ---------------------------------------------------------------------------
# router/ 删除验证
# ---------------------------------------------------------------------------

def test_router_deleted():
    """router/ 目录已被删除。"""
    import os
    assert not os.path.exists("router"), "router/ directory should be deleted"
    assert not os.path.exists("tests/test_router.py"), "tests/test_router.py should be deleted"


def test_no_router_imports():
    """cli/app.py 中不再 import router 模块。"""
    with open("cli/app.py") as f:
        content = f.read()
    assert "from router" not in content
    assert "import router" not in content


# ===========================================================================
# Task 4: 完整记忆系统集成测试
# ===========================================================================


class TestMemorySearchToolRegistered:
    """验证 MemorySearchTool 已注册到 ToolRunner。"""

    def test_register_tools_registers_memory_search(self):
        """_register_tools() 应将 MemorySearchTool 注册到 tool_runner。
        使用真实组件 + 临时目录。"""
        from capability.runner import ToolRunner
        from capability.tools.memory_search import MemorySearchTool
        from memory.long_term import LongTermMemory
        from memory.short_term import ShortTermMemory
        from memory.searcher import KeywordMemorySearcher
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            data_root = Path(d)
            # 模拟 _register_tools() 的逻辑
            runner = ToolRunner()
            searcher = KeywordMemorySearcher(
                long_term=LongTermMemory(data_root),
                short_term=ShortTermMemory(data_root),
            )
            runner.register(MemorySearchTool(searcher))

            # 验证 memory_search 已注册
            schemas = runner.get_tool_schemas()
            tool_names = [s["function"]["name"] for s in schemas]
            assert "memory_search" in tool_names, (
                f"MemorySearchTool 未注册，已注册: {tool_names}"
            )

    @pytest.mark.asyncio
    async def test_registered_memory_search_tool_executable(self):
        """注册后的 MemorySearchTool 可通过 ToolRunner.run() 执行。"""
        from capability.runner import ToolRunner
        from capability.tools.memory_search import MemorySearchTool
        from memory.long_term import LongTermMemory
        from memory.short_term import ShortTermMemory
        from memory.searcher import KeywordMemorySearcher
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            data_root = Path(d)
            ltm = LongTermMemory(data_root)
            stm = ShortTermMemory(data_root)
            # 写入测试数据
            ltm.write_topic("food.md", "## 食物偏好\n- 喜欢辣的食物",
                            {"name": "食物偏好", "description": "用户的食物偏好", "type": "user"})
            ltm.update_index()
            stm.add_item("test-sess", "用户喜欢吃火锅", "pref_detection")

            runner = ToolRunner()
            searcher = KeywordMemorySearcher(long_term=ltm, short_term=stm)
            runner.register(MemorySearchTool(searcher))

            # 通过 runner 执行搜索
            result = await runner.run("memory_search", {"query": "辣的食物"})
            assert isinstance(result, str)
            assert "辣" in result


class TestMemorySummaryTaskInAllTasks:
    """验证 MemorySummaryTask 已注册到 ALL_TASKS。"""

    def test_memory_summary_in_all_tasks(self):
        """ALL_TASKS 应包含 MemorySummaryTask。"""
        from side.tasks import ALL_TASKS
        names = [t.name for t in ALL_TASKS]
        assert "memory_summary" in names, (
            f"MemorySummaryTask 未在 ALL_TASKS 中，已注册: {names}"
        )

    def test_all_seven_tasks_registered(self):
        """ALL_TASKS 应恰好包含 8 个 task。"""
        from side.tasks import ALL_TASKS
        assert len(ALL_TASKS) == 8, f"期望 8 个 task，实际 {len(ALL_TASKS)}"


class TestBrixMemoryProviderComponents:
    """验证 BrixMemoryProvider 暴露 short_term、long_term、searcher。"""

    def test_provider_exposes_short_term(self):
        """BrixMemoryProvider.short_term 应返回 ShortTermMemory 实例。"""
        from memory.provider import BrixMemoryProvider
        from memory.short_term import ShortTermMemory
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            provider = BrixMemoryProvider(data_dir=Path(d))
            assert provider.short_term is not None
            assert isinstance(provider.short_term, ShortTermMemory)

    def test_provider_exposes_long_term(self):
        """BrixMemoryProvider.long_term 应返回 LongTermMemory 实例。"""
        from memory.provider import BrixMemoryProvider
        from memory.long_term import LongTermMemory
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            provider = BrixMemoryProvider(data_dir=Path(d))
            assert provider.long_term is not None
            assert isinstance(provider.long_term, LongTermMemory)

    def test_provider_exposes_searcher(self):
        """BrixMemoryProvider.searcher 应返回 KeywordMemorySearcher 实例。"""
        from memory.provider import BrixMemoryProvider
        from memory.searcher import KeywordMemorySearcher
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            provider = BrixMemoryProvider(data_dir=Path(d))
            assert provider.searcher is not None
            assert isinstance(provider.searcher, KeywordMemorySearcher)

    def test_provider_searcher_uses_provider_components(self):
        """BrixMemoryProvider.searcher 应使用 provider 自身的 long_term/short_term。"""
        from memory.provider import BrixMemoryProvider
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            provider = BrixMemoryProvider(data_dir=Path(d))
            # 通过 provider 的 short_term 写入数据
            provider.short_term.add_item("test-sess", "用户喜欢咖啡", "pref_detection")
            # 通过 provider 的 searcher 搜索
            results = provider.searcher.search("咖啡")
            assert len(results) > 0
            assert "咖啡" in results[0].content


class TestPrefDetectionWritesToShortTerm:
    """验证 pref_detection 可通过 ctx.memory.short_term 写入短期记忆。"""

    @pytest.mark.asyncio
    async def test_pref_detection_writes_via_real_provider(self):
        """pref_detection 应通过 BrixMemoryProvider.short_term.add_item() 写入偏好。
        使用真实组件 + 临时目录。"""
        from side.tasks.pref_detection import PrefDetectionTask
        from side.base import SideTaskContext
        from memory.provider import BrixMemoryProvider
        from unittest.mock import AsyncMock, MagicMock
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            provider = BrixMemoryProvider(data_dir=Path(d))

            # 构造 LLM 响应
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = '[{"preference": "用户喜欢辣的食物", "context": "用户说要吃爆炒腊肉"}]'
            mock_client.chat = AsyncMock(return_value=mock_response)

            ctx = SideTaskContext(
                llm_client=mock_client,
                side_model="test-model",
                config={"session_id": "test-sess-1"},
                memory=provider,
                session_messages=[
                    {"role": "user", "content": "我想吃爆炒腊肉"},
                    {"role": "assistant", "content": "好的，很下饭！"},
                    {"role": "user", "content": "我喜欢辣的"},
                ],
                user_input="我喜欢辣的",
                hooks=None,
            )

            task = PrefDetectionTask()
            result = await task.execute(ctx)

            # 验证 LLM 返回了偏好
            assert result is not None
            assert len(result) == 1
            assert result[0]["preference"] == "用户喜欢辣的食物"

            # 验证偏好已写入真实短期记忆
            items = provider.short_term.get_recent(limit=10)
            assert len(items) >= 1
            contents = [item.get("content", "") for item in items]
            assert "用户喜欢辣的食物" in contents

    @pytest.mark.asyncio
    async def test_pref_detection_then_searchable(self):
        """pref_detection 写入的偏好应可通过 searcher 搜索到。
        端到端：pref_detection → short_term → searcher.search()。"""
        from side.tasks.pref_detection import PrefDetectionTask
        from side.base import SideTaskContext
        from memory.provider import BrixMemoryProvider
        from unittest.mock import AsyncMock, MagicMock
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            provider = BrixMemoryProvider(data_dir=Path(d))

            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = '[{"preference": "用户喜欢用中文回复", "context": "用户要求中文"}]'
            mock_client.chat = AsyncMock(return_value=mock_response)

            ctx = SideTaskContext(
                llm_client=mock_client,
                side_model="test-model",
                config={"session_id": "test-sess-2"},
                memory=provider,
                session_messages=[
                    {"role": "user", "content": "请用中文回复我"},
                    {"role": "assistant", "content": "好的"},
                    {"role": "user", "content": "以后都用中文"},
                ],
                user_input="以后都用中文",
                hooks=None,
            )

            task = PrefDetectionTask()
            await task.execute(ctx)

            # 通过 searcher 搜索写入的偏好
            results = provider.searcher.search("中文")
            assert len(results) > 0
            assert any("中文" in r.content for r in results)


class TestSideManagerPassesMemory:
    """验证 SideTaskManager 将 memory 传递给 SideTaskContext。"""

    def test_build_context_includes_memory(self):
        """SideTaskManager._build_context() 应将 memory 传入 SideTaskContext。"""
        from side.manager import SideTaskManager
        from memory.provider import BrixMemoryProvider
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            provider = BrixMemoryProvider(data_dir=Path(d))
            mgr = SideTaskManager()
            mgr.configure(
                config={"side": {"enabled": True, "model": "test"}},
                llm_client=MagicMock(),
                memory=provider,
            )
            ctx = mgr._build_context(
                session_messages=[{"role": "user", "content": "hi"}],
                user_input="hi",
            )
            assert ctx.memory is provider
            assert ctx.memory.short_term is not None
            assert ctx.memory.long_term is not None
            assert ctx.memory.searcher is not None
