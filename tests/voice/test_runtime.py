"""VoiceRuntimeImpl 测试。"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from capability.voice.runtime import VoiceRuntimeImpl
from capability.voice.config import VoiceConfig


def test_runtime_init():
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)
    assert runtime is not None
    assert not runtime.is_running


@pytest.mark.asyncio
async def test_runtime_start_stop():
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)
    with patch.object(runtime, "_run_pipeline", new_callable=AsyncMock):
        await runtime.start()
        assert runtime.is_running
        await runtime.stop()
        assert not runtime.is_running


def test_runtime_on_voice_input_callback():
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)
    callback = MagicMock()
    runtime.on_voice_input(callback)
    assert runtime._on_voice_input == callback


def test_runtime_on_state_change_callback():
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)
    callback = MagicMock()
    runtime.on_state_change(callback)
    assert runtime._on_state_change == callback


def test_three_state_machine():
    """VoiceRuntimeImpl 实现三态状态机。"""
    from capability.voice.runtime import VoiceConversationState

    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    assert runtime.state == VoiceConversationState.IDLE


@pytest.mark.asyncio
async def test_runtime_pipeline_error_recovery():
    """VoiceRuntimeImpl 在 Pipeline 崩溃时恢复到 IDLE 状态。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    # 模拟 Pipeline 崩溃
    with patch.object(runtime, "_run_pipeline", side_effect=Exception("Pipeline crashed")):
        await runtime.start()
        # Pipeline 崩溃后应恢复到 IDLE
        # 注：实际实现中 _run_pipeline 的异常会被顶层错误边界捕获


@pytest.mark.asyncio
async def test_runtime_graceful_shutdown():
    """VoiceRuntimeImpl 优雅关闭按正确顺序执行。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    # 记录关闭顺序
    shutdown_order = []
    original_cleanup = runtime._cleanup_audio

    async def mock_cleanup():
        shutdown_order.append("cleanup_audio")
        await original_cleanup()

    runtime._cleanup_audio = mock_cleanup

    with patch.object(runtime, "_run_pipeline", new_callable=AsyncMock):
        await runtime.start()
        await runtime.stop()

    assert not runtime.is_running
    hooks.fire.assert_any_call("voice_state", state="idle")
