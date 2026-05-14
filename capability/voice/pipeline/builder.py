"""Pipeline builder — 组装 Voice Pipeline。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)

# interim 转录：连续静音超过此阈值时触发（约 400ms @ 32ms/chunk）
INTERIM_SILENCE_CHUNKS = 12


class SimpleVoicePipeline:
    """简单的语音 Pipeline — 顺序执行各处理器。"""

    def __init__(
        self,
        audio_source: Any,
        vad: Any,
        stt: Any,
        cleanup: Any,
        on_final_text: Optional[Callable] = None,
        on_interim_text: Optional[Callable] = None,
        hooks: Any = None,
        is_speaking: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._audio_source = audio_source
        self._vad = vad
        self._stt = stt
        self._cleanup = cleanup
        self._on_final_text = on_final_text
        self._on_interim_text = on_interim_text
        self._hooks = hooks
        self._is_speaking = is_speaking
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # interim 转录状态
        self._silence_chunks = 0
        self._speech_active = False
        self._interim_triggered = False  # 本轮 speech 是否已触发过 interim
        self._interim_task: Optional[asyncio.Task] = None

    @property
    def processors(self) -> List:
        return [self._audio_source, self._vad, self._stt, self._cleanup]

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Voice pipeline started")

    async def stop(self) -> None:
        self._running = False
        if self._interim_task is not None:
            self._interim_task.cancel()
            self._interim_task = None
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

                # 回声消除：TTS 播放期间跳过音频处理
                if self._is_speaking and self._is_speaking():
                    continue

                vad_frames = self._vad.process_frame_sync(audio_data)

                # 每个 chunk 都把原始音频送入 STT 缓冲区
                self._stt.process_frame_sync(type("AudioFrame", (), {"audio": audio_data})())

                # 追踪 VAD 状态用于 interim 转录
                self._update_speech_state(vad_frames)

                for frame in vad_frames:
                    if self._hooks:
                        self._hooks.fire("voice_state", state=frame.state)

                    if frame.state == "speech_start":
                        self._speech_active = True
                        self._silence_chunks = 0
                        self._interim_triggered = False

                    elif frame.state == "speech_end":
                        self._speech_active = False
                        self._silence_chunks = 0
                        self._interim_triggered = False
                        # 取消正在进行的 interim 任务
                        if self._interim_task is not None and not self._interim_task.done():
                            self._interim_task.cancel()
                            self._interim_task = None

                        import time as _time

                        # STT 转录（子进程运行，放线程池避免阻塞）
                        _t0 = _time.monotonic()
                        stt_frames = await asyncio.get_event_loop().run_in_executor(
                            None, self._stt.process_frame_sync, frame
                        )
                        _stt_ms = (_time.monotonic() - _t0) * 1000
                        if self._hooks:
                            self._hooks.fire("voice_timing", step="stt", ms=round(_stt_ms))

                        for stt_frame in stt_frames:
                            # LLM Cleanup
                            _t1 = _time.monotonic()
                            cleaned = await self._cleanup.process(stt_frame)
                            _cleanup_ms = (_time.monotonic() - _t1) * 1000
                            if self._hooks:
                                self._hooks.fire("voice_timing", step="cleanup", ms=round(_cleanup_ms))

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
            self._running = False
            if self._hooks:
                self._hooks.fire("voice_state", state="error", error=str(exc))

    def _update_speech_state(self, vad_frames: list) -> None:
        """追踪语音状态，触发 interim 转录。"""
        if not self._speech_active:
            return

        # 检查是否有 speech_start 帧（VAD 检测到语音）
        has_speech = any(
            hasattr(f, "audio") or (hasattr(f, "state") and f.state == "speech_start")
            for f in vad_frames
        )

        if has_speech:
            self._silence_chunks = 0
        else:
            self._silence_chunks += 1

        # 连续静音达到阈值且未触发过 interim → 触发 interim 转录
        if (
            self._silence_chunks >= INTERIM_SILENCE_CHUNKS
            and not self._interim_triggered
            and self._on_interim_text is not None
        ):
            self._interim_triggered = True
            audio = self._stt.get_buffer_audio()
            if audio and len(audio) > 16000:  # >0.5s
                self._interim_task = asyncio.ensure_future(
                    self._do_interim_transcription(audio)
                )

    async def _do_interim_transcription(self, audio: bytes) -> None:
        """在 executor 中执行 interim 转录。"""
        try:
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(
                None, self._stt.transcribe_interim, audio
            )
            if text and self._on_interim_text:
                self._on_interim_text(text)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("Interim transcription error: %s", exc)


def build_voice_pipeline(
    audio_source: Any,
    vad: Any,
    stt: Any,
    cleanup: Any,
    on_final_text: Optional[Callable] = None,
    on_interim_text: Optional[Callable] = None,
    hooks: Any = None,
    is_speaking: Optional[Callable[[], bool]] = None,
) -> SimpleVoicePipeline:
    """构建语音 Pipeline。"""
    return SimpleVoicePipeline(
        audio_source=audio_source,
        vad=vad,
        stt=stt,
        cleanup=cleanup,
        on_final_text=on_final_text,
        on_interim_text=on_interim_text,
        hooks=hooks,
        is_speaking=is_speaking,
    )
