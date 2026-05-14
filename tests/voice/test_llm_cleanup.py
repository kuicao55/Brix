"""LLMCleanupProcessor 测试。"""

import pytest
from unittest.mock import AsyncMock

from capability.voice.processors.llm_cleanup import LLMCleanupProcessor
from capability.voice.pipeline.frames import CleanedTextFrame, VoiceStateFrame


@pytest.mark.asyncio
async def test_cleanup_cleans_text():
    mock_llm = AsyncMock(return_value="你好世界，今天天气怎么样")
    cleanup = LLMCleanupProcessor(llm_fn=mock_llm)
    frame = CleanedTextFrame(text="嗯 你好世界 今天天气怎么样啊", raw_text="嗯 你好世界 今天天气怎么样啊")
    result = await cleanup.process(frame)
    assert result.text == "你好世界，今天天气怎么样"
    assert result.raw_text == "嗯 你好世界 今天天气怎么样啊"
    mock_llm.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_skips_short_text():
    mock_llm = AsyncMock()
    cleanup = LLMCleanupProcessor(llm_fn=mock_llm, min_length=5)
    frame = CleanedTextFrame(text="好的", raw_text="好的")
    result = await cleanup.process(frame)
    assert result.text == "好的"
    mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_handles_empty_result():
    mock_llm = AsyncMock(return_value="")
    cleanup = LLMCleanupProcessor(llm_fn=mock_llm)
    frame = CleanedTextFrame(text="嗯啊嗯啊嗯啊嗯啊嗯啊", raw_text="嗯啊嗯啊嗯啊嗯啊嗯啊")
    result = await cleanup.process(frame)
    assert result is None


@pytest.mark.asyncio
async def test_cleanup_timeout_fallback():
    import asyncio
    async def slow_llm(text):
        await asyncio.sleep(10)
        return "cleaned"
    cleanup = LLMCleanupProcessor(llm_fn=slow_llm, timeout=0.1)
    frame = CleanedTextFrame(text="嗯你好世界，今天天气怎么样啊", raw_text="嗯你好世界，今天天气怎么样啊")
    result = await cleanup.process(frame)
    assert result.text == "嗯你好世界，今天天气怎么样啊"


@pytest.mark.asyncio
async def test_cleanup_passes_non_text_frames():
    mock_llm = AsyncMock()
    cleanup = LLMCleanupProcessor(llm_fn=mock_llm)
    frame = VoiceStateFrame(state="speech_start")
    result = await cleanup.process(frame)
    assert isinstance(result, VoiceStateFrame)
    assert result.state == "speech_start"
