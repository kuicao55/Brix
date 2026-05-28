"""Pipeline builder — 组装 Voice Pipeline。"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from typing import Any, Callable, List, Optional

from capability.voice.pipeline.frames import VoiceStateFrame

logger = logging.getLogger(__name__)

# interim 转录：连续静音超过此阈值时触发（约 400ms @ 32ms/chunk）
INTERIM_SILENCE_CHUNKS = 12
# 周期性 interim：每累积约 0.25s 语音触发一次（8 chunks × 32ms ≈ 0.25s）
INTERIM_PERIODIC_CHUNKS = 8
# interim 最短音频：约 0.3s（16kHz * 2bytes）
INTERIM_MIN_AUDIO_BYTES = 9600
# interim 最大音频窗口：约 1.6s，避免越说越慢
INTERIM_MAX_AUDIO_BYTES = int(16000 * 2 * 1.6)
# 预滚动缓冲：保留最近约 256ms 音频，避免吞首字（8 * 32ms）
PREROLL_CHUNKS = 8


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
        cleanup_enabled: bool = True,
        post_speech_wait_ms: float = 1500,
    ) -> None:
        self._audio_source = audio_source
        self._vad = vad
        self._stt = stt
        self._cleanup = cleanup
        self._on_final_text = on_final_text
        self._on_interim_text = on_interim_text
        self._hooks = hooks
        self._is_speaking = is_speaking
        self._cleanup_enabled = cleanup_enabled
        self._post_speech_wait_sec = post_speech_wait_ms / 1000

        # 续说等待状态
        self._pending_speech_end_time: float | None = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # interim 转录状态
        self._silence_chunks = 0
        self._speech_active = False
        self._chunks_since_interim = 0  # 距上次 interim 的 chunk 数
        self._interim_task: Optional[asyncio.Task] = None
        self._interim_cancel: Optional[threading.Event] = None  # 显式取消信号
        self._utterance_id = 0  # 每轮 speech_start 递增，失效旧 interim
        self._preroll_audio: deque[bytes] = deque(maxlen=PREROLL_CHUNKS)

    @property
    def processors(self) -> List:
        return [self._audio_source, self._vad, self._stt, self._cleanup]

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Voice pipeline started")

    async def stop(self) -> None:
        self._running = False
        self._cancel_interim()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Voice pipeline stopped")

    async def _process_loop(self) -> None:
        import time as _time

        try:
            while self._running:
                try:
                    audio_data = await asyncio.wait_for(
                        self._audio_source.audio_queue.get(),
                        timeout=0.1,
                    )
                except asyncio.TimeoutError:
                    # 超时也检查续说等待是否到期
                    await self._check_pending_speech_end()
                    continue

                self._preroll_audio.append(audio_data)

                # 回声消除：TTS 播放期间跳过音频处理
                if self._is_speaking and self._is_speaking():
                    # TTS 期间也取消待处理的 speech_end，避免 TTS 结束后立即处理旧语音
                    self._pending_speech_end_time = None
                    continue

                vad_frames = self._vad.process_frame_sync(audio_data)

                # 只在语音活跃时缓冲音频，避免前导静音送入 STT
                if self._speech_active:
                    self._stt.process_frame_sync(
                        type("AudioFrame", (), {"audio": audio_data})()
                    )

                # 追踪 VAD 状态用于 interim 转录
                self._update_speech_state(vad_frames)

                for frame in vad_frames:
                    if self._hooks:
                        self._hooks.fire("voice_state", state=frame.state)

                    if frame.state == "speech_start":
                        # 续说：取消待处理的 speech_end，继续收集
                        if self._pending_speech_end_time is not None:
                            logger.info("Speech resumed during wait window, cancelling pending end")
                            self._pending_speech_end_time = None

                        self._cancel_interim()
                        self._utterance_id += 1
                        self._speech_active = True
                        self._silence_chunks = 0
                        self._chunks_since_interim = 0
                        # speech_start 时清空 STT 缓冲区中的噪声
                        self._stt.reset()
                        # 将触发前的预缓冲一并送入 STT，避免首字被吞
                        for preroll_chunk in self._preroll_audio:
                            self._stt.process_frame_sync(
                                type("AudioFrame", (), {"audio": preroll_chunk})()
                            )

                    elif frame.state == "speech_end":
                        self._utterance_id += 1
                        self._speech_active = False
                        self._silence_chunks = 0
                        self._chunks_since_interim = 0
                        self._cancel_interim()

                        # 不立即处理，进入续说等待窗口
                        self._pending_speech_end_time = _time.monotonic()
                        logger.info("Speech end detected, waiting %.0fms for continuation...",
                                   self._post_speech_wait_sec * 1000)

                # 检查续说等待是否到期
                await self._check_pending_speech_end()

        except asyncio.CancelledError:
            logger.info("Voice pipeline loop cancelled")
        except Exception as exc:
            logger.error("Voice pipeline error: %s", exc, exc_info=True)
            self._running = False
            if self._hooks:
                self._hooks.fire("voice_state", state="error", error=str(exc))

    async def _check_pending_speech_end(self) -> None:
        """检查续说等待是否到期，到期则处理 STT。"""
        import time as _time

        if self._pending_speech_end_time is None:
            return

        elapsed = _time.monotonic() - self._pending_speech_end_time
        if elapsed < self._post_speech_wait_sec:
            return  # 还在等待中

        # 等待到期，处理 STT
        self._pending_speech_end_time = None
        logger.info("Continuation wait expired, processing STT...")

        frame = VoiceStateFrame(state="speech_end")

        _t0 = _time.monotonic()
        stt_frames = await asyncio.get_event_loop().run_in_executor(
            None, self._stt.process_frame_sync, frame
        )
        _stt_ms = (_time.monotonic() - _t0) * 1000
        if self._hooks:
            self._hooks.fire("voice_timing", step="stt", ms=round(_stt_ms))

        if not stt_frames:
            logger.warning("STT returned empty (timeout or error), resetting state")
            if self._hooks:
                self._hooks.fire("voice_state", state="idle")
            return

        for stt_frame in stt_frames:
            if self._cleanup_enabled:
                _t1 = _time.monotonic()
                cleaned = await self._cleanup.process(stt_frame)
                _cleanup_ms = (_time.monotonic() - _t1) * 1000
                if self._hooks:
                    self._hooks.fire("voice_timing", step="cleanup", ms=round(_cleanup_ms))
            else:
                cleaned = stt_frame

            if cleaned is not None:
                if self._hooks:
                    self._hooks.fire(
                        "voice_input",
                        text=cleaned.text,
                        raw=cleaned.raw_text,
                    )
                if self._on_final_text:
                    self._on_final_text(cleaned.text)

    def _update_speech_state(self, vad_frames: list) -> None:
        """追踪语音状态，周期性触发 interim 转录。"""
        if not self._speech_active:
            return

        self._chunks_since_interim += 1

        # 检查是否有 speech 帧
        has_speech = any(
            hasattr(f, "audio") or (hasattr(f, "state") and f.state == "speech_start")
            for f in vad_frames
        )

        if has_speech:
            self._silence_chunks = 0
        else:
            self._silence_chunks += 1

        # 触发条件：周期性（每 ~1.5s）或 自然停顿（~400ms 静音）
        should_trigger = (
            self._chunks_since_interim >= INTERIM_PERIODIC_CHUNKS
            or self._silence_chunks >= INTERIM_SILENCE_CHUNKS
        )

        if should_trigger and self._on_interim_text is not None:
            # 同一时刻仅允许一个 interim 请求，避免 worker 堆积旧任务
            if self._interim_task is not None and not self._interim_task.done():
                return
            audio = self._stt.get_buffer_audio()
            if audio and len(audio) >= INTERIM_MIN_AUDIO_BYTES:
                interim_audio = audio[-INTERIM_MAX_AUDIO_BYTES:]
                self._chunks_since_interim = 0
                self._silence_chunks = 0
                # 创建新的取消信号并启动任务
                self._interim_cancel = threading.Event()
                self._interim_task = asyncio.create_task(
                    self._do_interim_transcription(
                        interim_audio,
                        self._interim_cancel,
                        self._utterance_id,
                    )
                )

    def _cancel_interim(self) -> None:
        """取消正在进行的 interim 任务。"""
        if self._interim_cancel is not None:
            self._interim_cancel.set()
            self._interim_cancel = None
        task = self._interim_task
        self._interim_task = None
        if task is not None and not task.done():
            task.cancel()

    async def _do_interim_transcription(
        self,
        audio: bytes,
        cancel: threading.Event,
        utterance_id: int,
    ) -> None:
        """在 executor 中执行 interim 转录。"""
        try:
            if cancel.is_set():
                return
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(
                None, self._stt.transcribe_interim, audio, cancel
            )
            if cancel.is_set():
                return
            # 话轮已变化或已结束：丢弃过期 interim，避免最终发送后仍刷新文本
            if utterance_id != self._utterance_id or not self._speech_active:
                return
            logger.info("Interim result: '%s' (callback=%s)", text[:30] if text else "", self._on_interim_text is not None)
            if text and self._on_interim_text:
                self._on_interim_text(text)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("Interim transcription error: %s", exc)
        finally:
            if self._interim_cancel is cancel:
                self._interim_cancel = None
            current = asyncio.current_task()
            if current is not None and self._interim_task is current:
                self._interim_task = None


def build_voice_pipeline(
    audio_source: Any,
    vad: Any,
    stt: Any,
    cleanup: Any,
    on_final_text: Optional[Callable] = None,
    on_interim_text: Optional[Callable] = None,
    hooks: Any = None,
    is_speaking: Optional[Callable[[], bool]] = None,
    cleanup_enabled: bool = True,
    post_speech_wait_ms: float = 1500,
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
        cleanup_enabled=cleanup_enabled,
        post_speech_wait_ms=post_speech_wait_ms,
    )
