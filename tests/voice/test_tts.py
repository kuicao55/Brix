"""TTSProcessor 测试。"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from capability.voice.processors.tts import TTSProcessor, split_sentences


def test_split_sentences_basic():
    """split_sentences 按句号切分。"""
    text = "你好，我是Brix。今天天气怎么样？"
    result = split_sentences(text)
    assert len(result) == 2
    assert result[0] == "你好，我是Brix。"
    assert result[1] == "今天天气怎么样？"


def test_split_sentences_short_merge():
    """split_sentences 合并短句。"""
    text = "嗯。你好世界。"
    result = split_sentences(text)
    # "嗯。" 太短（<3字），应合并到下一句
    assert len(result) == 1
    assert result[0] == "嗯。你好世界。"


def test_split_sentences_no_punctuation():
    """split_sentences 处理无标点文本。"""
    text = "这是一段没有标点的文本"
    result = split_sentences(text)
    assert len(result) == 1
    assert result[0] == "这是一段没有标点的文本"


def test_split_sentences_empty():
    """split_sentences 处理空文本。"""
    result = split_sentences("")
    assert result == []


def test_split_sentences_filler_only():
    """split_sentences 处理纯口头禅。"""
    text = "嗯嗯嗯"
    result = split_sentences(text)
    assert result == ["嗯嗯嗯"]


@pytest.mark.asyncio
async def test_tts_processor_synthesize():
    """TTSProcessor 对文本进行流式合成。"""
    # 模拟 CosyVoice 返回 PCM chunks
    async def mock_tts(text):
        yield b"\x00\x01" * 100  # chunk 1
        yield b"\x02\x03" * 100  # chunk 2

    tts = TTSProcessor(tts_fn=mock_tts, prefetch_ms=0)  # 测试时禁用预缓冲
    audio_chunks = []

    async for chunk in tts.synthesize("你好世界"):
        audio_chunks.append(chunk)

    assert len(audio_chunks) == 2
    assert audio_chunks[0] == b"\x00\x01" * 100
    assert audio_chunks[1] == b"\x02\x03" * 100


@pytest.mark.asyncio
async def test_tts_processor_multisentence():
    """TTSProcessor 对多句文本逐句合成。"""
    call_count = 0

    async def mock_tts(text):
        nonlocal call_count
        call_count += 1
        yield b"\x00" * 10

    tts = TTSProcessor(tts_fn=mock_tts, prefetch_ms=0)
    async for _ in tts.synthesize("第一句。第二句。"):
        pass

    assert call_count == 2  # 两次调用，每次一句


@pytest.mark.asyncio
async def test_tts_processor_prefetch_buffer():
    """TTSProcessor 预缓冲区在积累足够数据后才输出。"""
    async def mock_tts(text):
        # 每次返回少量数据
        for _ in range(10):
            yield b"\x00" * 10  # 10 bytes

    tts = TTSProcessor(tts_fn=mock_tts, prefetch_ms=80)  # 80ms 预缓冲
    # 24kHz, 16bit = 48000 bytes/sec. 80ms = 3840 bytes
    chunks = []
    async for chunk in tts.synthesize("测试预缓冲"):
        chunks.append(chunk)

    # 应该有输出（预缓冲后）
    assert len(chunks) > 0
