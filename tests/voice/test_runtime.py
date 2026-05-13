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
