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
    """split_sentences 合并短句（<5字）。"""
    text = "啊啊啊。你好世界。"
    result = split_sentences(text)
    # "啊啊啊。" 4字（<5字），应合并到下一句
    assert len(result) == 1
    assert result[0] == "啊啊啊。你好世界。"


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
    async for _ in tts.synthesize("这是第一句话。这是第二句话。"):
        pass

    assert call_count == 2  # 两次调用，每次一句


@pytest.mark.asyncio
async def test_tts_processor_prefetch_buffer():
    """TTSProcessor 预缓冲区在积累足够数据后才输出。

    验证：
    1. 首个输出 chunk >= 3840 字节（缓冲区倾倒）
    2. 后续 chunk 为 100 字节（直通）
    3. 总输出 chunk 数 < 50（证明发生了缓冲，非直通）
    """
    async def mock_tts(text):
        for _ in range(50):
            yield b"\x00" * 100  # 每次 100 字节，共 5000 字节

    tts = TTSProcessor(tts_fn=mock_tts, prefetch_ms=80)
    # 24kHz, 16bit = 48000 bytes/sec. 80ms = 3840 bytes
    chunks = []
    async for chunk in tts.synthesize("测试预缓冲"):
        chunks.append(chunk)

    # 首个 chunk 应 >= 3840 字节（缓冲区倾倒）
    assert len(chunks[0]) >= 3840, (
        f"首个 chunk 应 >= 3840 字节，实际 {len(chunks[0])}"
    )
    # 后续 chunk 应为 100 字节（直通）
    for chunk in chunks[1:]:
        assert len(chunk) == 100, f"后续 chunk 应为 100 字节，实际 {len(chunk)}"
    # 总 chunk 数 < 50（证明缓冲合并了数据）
    assert len(chunks) < 50, f"总 chunk 数应 < 50，实际 {len(chunks)}"


@pytest.mark.asyncio
async def test_tts_processor_synthesize_to_queue():
    """TTSProcessor.synthesize_to_queue 将 chunks 放入队列并以 None 结尾。"""
    call_count = 0

    async def mock_tts(text):
        nonlocal call_count
        call_count += 1
        yield b"\x00\x01" * 50  # chunk 1
        yield b"\x02\x03" * 50  # chunk 2

    tts = TTSProcessor(tts_fn=mock_tts, prefetch_ms=0)
    queue: asyncio.Queue = asyncio.Queue()

    await tts.synthesize_to_queue("这是第一句话。这是第二句话。", queue)

    # 从队列收集所有 items
    items = []
    while True:
        item = await queue.get()
        if item is None:
            break
        items.append(item)

    # 多句文本应触发两次 tts_fn 调用
    assert call_count == 2, f"应调用 2 次 tts_fn，实际 {call_count}"
    # 每句产出 2 个 chunk，共 4 个
    assert len(items) == 4, f"应有 4 个 chunk，实际 {len(items)}"
    # 验证 chunk 内容
    assert items[0] == b"\x00\x01" * 50
    assert items[1] == b"\x02\x03" * 50
    assert items[2] == b"\x00\x01" * 50
    assert items[3] == b"\x02\x03" * 50
    # 队列应为空（None 已被消费）
    assert queue.empty()
