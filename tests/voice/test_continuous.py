"""连续对话模式测试。"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from capability.voice.runtime import VoiceRuntimeImpl, VoiceConversationState
from capability.voice.config import VoiceConfig


def test_continuous_mode_initial_state():
    """连续对话模式初始状态为 IDLE。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    assert runtime.state == VoiceConversationState.IDLE
    assert runtime._continuous is False


def test_on_tts_complete_continuous_transitions_to_sleeping():
    """连续模式下 TTS 完成后进入 SLEEPING 状态。"""
    cfg = VoiceConfig(continuous_idle_timeout=10.0)
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)
    runtime._continuous = True
    runtime._running = True
    runtime._state = VoiceConversationState.SPEAKING

    runtime._on_tts_complete()

    assert runtime.state == VoiceConversationState.SLEEPING
    hooks.fire.assert_called_with("voice_state", state="sleeping")

    # 清理泄漏的 asyncio task
    if runtime._idle_timeout_task is not None:
        runtime._idle_timeout_task.cancel()


def test_on_tts_complete_non_continuous_transitions_to_idle():
    """非连续模式下 TTS 完成后回到 IDLE 状态。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)
    runtime._continuous = False
    runtime._running = True
    runtime._state = VoiceConversationState.SPEAKING

    runtime._on_tts_complete()

    assert runtime.state == VoiceConversationState.IDLE
    hooks.fire.assert_called_with("voice_state", state="idle")


@pytest.mark.asyncio
async def test_idle_timeout_returns_to_idle():
    """连续模式下空闲超时回到 IDLE。"""
    cfg = VoiceConfig(continuous_idle_timeout=0.1)  # 100ms 超时
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)
    runtime._continuous = True
    runtime._running = True
    runtime._state = VoiceConversationState.SLEEPING

    # 启动超时检测
    runtime._start_idle_timeout()

    # 等待超时
    await asyncio.sleep(0.2)

    assert runtime.state == VoiceConversationState.IDLE

    # 清理
    if runtime._idle_timeout_task is not None:
        runtime._idle_timeout_task.cancel()
        try:
            await runtime._idle_timeout_task
        except asyncio.CancelledError:
            pass


def test_handle_voice_detected_cancels_timeout():
    """检测到语音输入时取消超时任务。"""
    cfg = VoiceConfig(continuous_idle_timeout=10.0)
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)
    runtime._continuous = True
    runtime._running = True
    runtime._state = VoiceConversationState.SLEEPING

    # 模拟超时任务存在
    mock_task = MagicMock()
    mock_task.cancel = MagicMock()
    runtime._idle_timeout_task = mock_task

    runtime._handle_voice_detected()

    mock_task.cancel.assert_called_once()
    assert runtime._idle_timeout_task is None
    assert runtime.state == VoiceConversationState.LISTENING


def test_handle_voice_detected_no_task():
    """无超时任务时 _handle_voice_detected 仍切换到 LISTENING。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)
    runtime._state = VoiceConversationState.SLEEPING
    runtime._idle_timeout_task = None

    runtime._handle_voice_detected()

    assert runtime.state == VoiceConversationState.LISTENING


@pytest.mark.asyncio
async def test_start_stores_continuous_flag():
    """start(continuous=True) 存储 continuous 标志。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    with patch.object(runtime, '_run_pipeline', new_callable=AsyncMock):
        await runtime.start(continuous=True)
        assert runtime._continuous is True
        assert runtime.is_running is True

    # 清理
    runtime._running = False


@pytest.mark.asyncio
async def test_stop_cancels_idle_timeout():
    """stop() 取消空闲超时任务，不触发残留 hook。"""
    cfg = VoiceConfig(continuous_idle_timeout=5.0)
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)
    runtime._continuous = True
    runtime._running = True
    runtime._state = VoiceConversationState.SPEAKING

    # 触发 TTS 完成，进入 SLEEPING 并启动超时
    runtime._on_tts_complete()
    assert runtime._idle_timeout_task is not None

    hooks.reset_mock()
    await runtime.stop()

    assert runtime._idle_timeout_task is None
    # stop 应该只触发一次 idle hook（来自 stop 本身），超时不应再触发
    idle_calls = [c for c in hooks.fire.call_args_list if c == (("voice_state",), {"state": "idle"})]
    assert len(idle_calls) == 1


@pytest.mark.asyncio
async def test_idle_timeout_respects_shutdown():
    """_idle_timeout_loop 在 _shutdown 状态下不触发 hook。"""
    cfg = VoiceConfig(continuous_idle_timeout=0.1)
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)
    runtime._continuous = True
    runtime._running = True
    runtime._shutdown = True
    runtime._state = VoiceConversationState.SLEEPING

    # 手动调用超时循环
    await runtime._idle_timeout_loop()

    # 不应触发任何 hook
    hooks.fire.assert_not_called()
    # 状态不变
    assert runtime.state == VoiceConversationState.SLEEPING
