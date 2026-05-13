"""TTSProcessor — 阿里云 CosyVoice v3 Flash 流式语音合成。

策略：按句切分、逐句合成、80ms 预缓冲后输出。
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import AsyncIterator, Callable

logger = logging.getLogger(__name__)


def split_sentences(text: str) -> list[str]:
    """按句子边界切分文本。

    规则：句号、问号、感叹号、分号后切分。
    短句（<5字）合并到下一句，避免碎片合成。
    """
    if not text.strip():
        return []

    raw = re.split(r'([。！？；\n])', text)
    sentences = []
    buf = ""
    for part in raw:
        buf += part
        if re.match(r'[。！？；\n]', part):
            if len(buf.strip()) >= 5:
                sentences.append(buf.strip())
                buf = ""
            # 短句留在 buf 中，与下一句合并
    if buf.strip():
        if sentences:
            if len(buf.strip()) < 5:
                sentences[-1] += buf.strip()
            else:
                sentences.append(buf.strip())
        else:
            sentences.append(buf.strip())
    return sentences


class TTSProcessor:
    """CosyVoice 流式语音合成处理器。

    按句切分 → 逐句合成 → 预缓冲 → 输出 PCM chunks。
    """

    def __init__(
        self,
        tts_fn: Callable[[str], AsyncIterator[bytes]],
        sample_rate: int = 24000,
        bytes_per_sample: int = 2,  # int16
        prefetch_ms: int = 80,
    ) -> None:
        self._tts_fn = tts_fn
        self._sample_rate = sample_rate
        self._bytes_per_sample = bytes_per_sample
        self._prefetch_bytes = int(sample_rate * prefetch_ms / 1000) * bytes_per_sample

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """流式合成文本，yield PCM chunks。"""
        sentences = split_sentences(text)
        if not sentences:
            logger.debug("TTS: empty text, skip")
            return

        logger.debug("TTS: synthesizing %d sentences", len(sentences))

        for i, sentence in enumerate(sentences):
            logger.debug("TTS: sentence %d/%d: %s", i + 1, len(sentences), sentence[:30])
            buffer = bytearray()
            prefetch_done = self._prefetch_bytes <= 0  # prefetch_ms=0 时跳过预缓冲

            async for chunk in self._tts_fn(sentence):
                if not prefetch_done:
                    buffer.extend(chunk)
                    if len(buffer) >= self._prefetch_bytes:
                        prefetch_done = True
                        yield bytes(buffer)
                        buffer.clear()
                else:
                    yield chunk

            # flush 残余 buffer
            if buffer:
                yield bytes(buffer)

    async def synthesize_to_queue(self, text: str, queue: asyncio.Queue) -> None:
        """合成文本并将 chunks 放入队列。供 Pipeline 使用。"""
        async for chunk in self.synthesize(text):
            await queue.put(chunk)
        await queue.put(None)  # 结束标记
