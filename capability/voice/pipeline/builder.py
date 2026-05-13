"""Pipeline builder — 组装 Voice Pipeline。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


class SimpleVoicePipeline:
    """简单的语音 Pipeline — 顺序执行各处理器。"""

    def __init__(
        self,
        audio_source: Any,
        vad: Any,
        stt: Any,
        cleanup: Any,
        on_final_text: Optional[Callable] = None,
        hooks: Any = None,
    ) -> None:
        self._audio_source = audio_source
        self._vad = vad
        self._stt = stt
        self._cleanup = cleanup
        self._on_final_text = on_final_text
        self._hooks = hooks
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @property
    def processors(self) -> List:
        return [self._audio_source, self._vad, self._stt, self._cleanup]

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Voice pipeline started")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Voice pipeline stopped")

    async def _process_loop(self) -> None:
        try:
            while self._running:
                try:
                    audio_data = await asyncio.wait_for(
                        self._audio_source.audio_queue.get(),
                        timeout=0.1,
                    )
                except asyncio.TimeoutError:
                    continue

                vad_frames = self._vad.process_frame_sync(audio_data)
                for frame in vad_frames:
                    if self._hooks:
                        self._hooks.fire("voice_state", state=frame.state)

                for frame in vad_frames:
                    stt_frames = self._stt.process_frame_sync(frame)
                    for stt_frame in stt_frames:
                        cleaned = await self._cleanup.process(stt_frame)
                        if cleaned is not None:
                            if self._hooks:
                                self._hooks.fire(
                                    "voice_input",
                                    text=cleaned.text,
                                    raw=cleaned.raw_text,
                                )
                            if self._on_final_text:
                                self._on_final_text(cleaned.text)

        except asyncio.CancelledError:
            logger.info("Voice pipeline loop cancelled")
        except Exception as exc:
            logger.error("Voice pipeline error: %s", exc, exc_info=True)
            if self._hooks:
                self._hooks.fire("voice_state", state="error", error=str(exc))


def build_voice_pipeline(
    audio_source: Any,
    vad: Any,
    stt: Any,
    cleanup: Any,
    on_final_text: Optional[Callable] = None,
    hooks: Any = None,
) -> SimpleVoicePipeline:
    """构建语音 Pipeline。"""
    return SimpleVoicePipeline(
        audio_source=audio_source,
        vad=vad,
        stt=stt,
        cleanup=cleanup,
        on_final_text=on_final_text,
        hooks=hooks,
    )
