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

    # 初始状态为 IDLE
    assert runtime.state == VoiceConversationState.IDLE

    # _handle_final_text 将状态转换为 PROCESSING
    runtime._handle_final_text("test input")
    assert runtime.state == VoiceConversationState.PROCESSING

    # _on_voice_input 回调被触发
    callback = MagicMock()
    runtime.on_voice_input(callback)
    runtime._handle_final_text("hello world")
    callback.assert_called_once_with("hello world")


def test_runtime_tts_candidate_filter():
    """TTS 候选过滤应拦截无意义短片段。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    assert runtime._is_tts_candidate("你好") is True
    assert runtime._is_tts_candidate("...") is False
    assert runtime._is_tts_candidate('"" ——""""') is False
    assert runtime._is_tts_candidate("bug") is False
    assert runtime._is_tts_candidate("bug fixes today") is True


@pytest.mark.asyncio
async def test_runtime_pipeline_error_recovery():
    """VoiceRuntimeImpl 在 Pipeline 崩溃时恢复到 IDLE 状态。"""
    from capability.voice.runtime import VoiceConversationState

    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    # 模拟 Pipeline 崩溃
    with patch.object(runtime, "_run_pipeline", side_effect=Exception("Pipeline crashed")):
        await runtime.start()

    # Pipeline 崩溃后应恢复到 IDLE
    assert runtime.state == VoiceConversationState.IDLE
    assert not runtime.is_running
    hooks.fire.assert_any_call("voice_state", state="error", error="Pipeline crashed")


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
    assert "cleanup_audio" in shutdown_order
    hooks.fire.assert_any_call("voice_state", state="idle")


@pytest.mark.asyncio
async def test_runtime_tts_empty_audio_fires_error_hook():
    """CosyVoice 无音频输出时应触发 empty_audio 错误。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    async def _empty_synthesize(_text: str):
        if False:
            yield b""

    runtime._tts_client = MagicMock()
    runtime._tts_client.synthesize = _empty_synthesize
    runtime._audio_player = MagicMock()
    runtime._audio_player.is_active = False
    runtime._shutdown = False
    runtime._speak_with_system_tts = AsyncMock(return_value=False)

    await runtime._synthesize_and_speak("测试")

    err_calls = [c for c in hooks.fire.call_args_list if c.args and c.args[0] == "voice_tts_error"]
    assert any(c.kwargs.get("error") == "tts_empty_audio" for c in err_calls)


@pytest.mark.asyncio
async def test_runtime_uses_system_tts_fallback_when_no_player():
    """无播放器时应优先使用系统 TTS 兜底。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    runtime._audio_player = None
    runtime._shutdown = False
    runtime._speak_with_system_tts = AsyncMock(return_value=True)
    runtime._pcm_playback_available = MagicMock(return_value=False)

    await runtime._synthesize_and_speak("你好")

    runtime._speak_with_system_tts.assert_awaited_once_with("你好")
    tts_calls = [c for c in hooks.fire.call_args_list if c.args and c.args[0] == "voice_tts"]
    assert any(c.kwargs.get("chars") == 2 for c in tts_calls)


@pytest.mark.asyncio
async def test_runtime_uses_afplay_for_cosyvoice_pcm_without_pyaudio():
    """无 PyAudio 时仍应调用 CosyVoice，并用 afplay 播放 PCM。"""
    cfg = VoiceConfig()
    hooks = MagicMock()
    llm_fn = AsyncMock()
    runtime = VoiceRuntimeImpl(config=cfg, hooks=hooks, llm_fn=llm_fn)

    async def _pcm_synthesize(_text: str):
        yield b"\x00\x01" * 200

    runtime._tts_client = MagicMock()
    runtime._tts_client.synthesize = _pcm_synthesize
    runtime._audio_player = None
    runtime._shutdown = False
    runtime._play_pcm_with_afplay = AsyncMock(return_value=True)

    await runtime._synthesize_and_speak("你好")

    runtime._play_pcm_with_afplay.assert_awaited_once()
    tts_calls = [c for c in hooks.fire.call_args_list if c.args and c.args[0] == "voice_tts"]
    assert any(c.kwargs.get("chars") == 2 for c in tts_calls)
