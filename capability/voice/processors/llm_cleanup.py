"""LLMCleanupProcessor — 利用 Brix 的 LLM 对语音识别文本做润色。"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from capability.voice.pipeline.frames import CleanedTextFrame, VoiceStateFrame

logger = logging.getLogger(__name__)

CLEANUP_SYSTEM_PROMPT = """你是语音文本润色器。你的唯一任务是将语音识别（ASR）的原始输出整理为干净的书面文本。

规则：
1. 去除口头禅和填充词：嗯、啊、呃、那个、就是说、然后的话、怎么说呢、对对对、是是是
2. 补全缺失的标点符号（句号、逗号、问号、感叹号）
3. 纠正明显的同音字/语音识别错误（如"在那"→"在哪"，根据上下文判断）
4. 保留原始语义和措辞，不改写内容，不添加信息
5. 如果原文已经是干净文本，直接原样返回
6. 如果原文为空或只有口头禅，返回空字符串

只返回润色后的文本。不要解释、不要加引号、不要加任何前缀。"""


class LLMCleanupProcessor:
    """LLM 语音润色处理器。"""

    def __init__(
        self,
        llm_fn: Callable[[str], Awaitable[str]],
        timeout: float = 2.0,
        min_length: int = 4,
    ) -> None:
        self._llm_fn = llm_fn
        self._timeout = timeout
        self._min_length = min_length

    async def process(self, frame):
        """处理帧 — 只对 CleanedTextFrame 做 LLM 润色，其他帧直接透传。"""
        if not isinstance(frame, CleanedTextFrame):
            return frame

        raw_text = frame.raw_text or frame.text

        if len(raw_text) < self._min_length:
            logger.debug("Cleanup skipped (short text): %s", raw_text)
            return frame

        prompt = f"{CLEANUP_SYSTEM_PROMPT}\n\n原文：{raw_text}"
        try:
            cleaned = await asyncio.wait_for(
                self._llm_fn(prompt),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Cleanup timeout (%.1fs), using raw text", self._timeout)
            return frame
        except Exception as exc:
            logger.error("Cleanup error: %s, using raw text", exc)
            return frame

        cleaned = cleaned.strip()

        if not cleaned:
            logger.debug("Cleanup returned empty (filler words)")
            return None

        return CleanedTextFrame(text=cleaned, raw_text=raw_text)
