"""CLI 语音集成测试 — 测试真实代码路径。"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from capability.voice.config import VoiceConfig
from capability.voice.runtime import VoiceRuntimeImpl, VoiceConversationState


def test_handle_voice_input_queues_text():
    """BrixCLI._handle_voice_input 将文本放入 _voice_input_queue。"""
    from cli.app import BrixCLI

    mock_mem = MagicMock()
    mock_mem.build_system_prompt.return_value = ""
    mock_mem.get_context_messages.return_value = []

    with patch("cli.app.load_config", return_value={
        "routing": {"default_model": "test-model"},
        "memory": {"max_context_tokens": 8000, "data_dir": "/tmp/test_brix"},
    }), patch("cli.app.create_memory_provider", return_value=mock_mem):
        cli = BrixCLI()

    # 队列初始为空
    assert cli._voice_input_queue.empty()

    # 调用回调
    cli._handle_voice_input("你好世界")

    # 队列中应有文本
    assert not cli._voice_input_queue.empty()
    text = cli._voice_input_queue.get_nowait()
    assert text == "你好世界"


def test_voice_queue_competition():
    """语音队列和键盘任务通过 asyncio.wait 竞争 — 使用真实队列。"""
    queue = asyncio.Queue()

    async def run_test():
        # 模拟语音输入先到
        queue.put_nowait("语音输入")

        async def keyboard_input():
            await asyncio.sleep(0.1)
            return "键盘输入"

        voice_task = asyncio.create_task(queue.get())
        keyboard_task = asyncio.create_task(keyboard_input())

        done, pending = await asyncio.wait(
            [keyboard_task, voice_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        result = done.pop().result()
        assert result == "语音输入"

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.get_event_loop().run_until_complete(run_test())


def test_feed_response_text_when_not_running():
    """VoiceRuntimeImpl.feed_response_text 在未运行时为 no-op。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    # 未运行状态，不应抛异常
    runtime.feed_response_text("测试文本")
    # 无异常即通过


def test_feed_response_text_when_shutdown():
    """VoiceRuntimeImpl.feed_response_text 在 shutdown 状态为 no-op。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    runtime._shutdown = True
    runtime._running = True

    # shutdown 状态，不应抛异常
    runtime.feed_response_text("测试文本")


def test_init_voice_disabled_by_default():
    """BrixCLI 在无 voice.enabled 配置时 _voice 为 None。"""
    from cli.app import BrixCLI

    mock_mem = MagicMock()
    mock_mem.build_system_prompt.return_value = ""
    mock_mem.get_context_messages.return_value = []

    with patch("cli.app.load_config", return_value={
        "routing": {"default_model": "test-model"},
        "memory": {"max_context_tokens": 8000, "data_dir": "/tmp/test_brix"},
    }), patch("cli.app.create_memory_provider", return_value=mock_mem):
        cli = BrixCLI()

    assert cli._voice is None
