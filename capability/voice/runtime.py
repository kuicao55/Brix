"""VoiceRuntimeImpl — 语音运行时实现。"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Callable, Optional

from capability.voice.config import VoiceConfig
from capability.voice.pipeline.builder import build_voice_pipeline
from capability.voice.processors.llm_cleanup import LLMCleanupProcessor
from capability.voice.processors.stt import STTProcessor
from capability.voice.processors.vad import VADProcessor
from capability.voice.protocol import VoiceRuntime
from capability.voice.transport.local_audio import LocalAudioTransport

logger = logging.getLogger(__name__)


class VoiceConversationState(Enum):
    """语音对话状态机。"""
    IDLE = "idle"
    SLEEPING = "sleeping"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


class VoiceRuntimeImpl:
    """语音运行时实现 — 管理 Pipeline 生命周期。"""

    def __init__(
        self,
        config: VoiceConfig,
        hooks: Any,
        llm_fn: Callable,
        tts_client: Any = None,
    ) -> None:
        self._config = config
        self._hooks = hooks
        self._llm_fn = llm_fn
        self._tts_client = tts_client
        self._running = False
        self._shutdown = False
        self._continuous = False
        self._state = VoiceConversationState.IDLE

        self._on_voice_input: Optional[Callable[[str], None]] = None
        self._on_state_change: Optional[Callable[[str], None]] = None

        self._transport: Optional[LocalAudioTransport] = None
        self._vad: Optional[VADProcessor] = None
        self._stt: Optional[STTProcessor] = None
        self._cleanup: Optional[LLMCleanupProcessor] = None
        self._pipeline: Any = None
        self._idle_timeout_task: Optional[asyncio.Task] = None
        self._tts_buffer: str = ""  # TTS 文本累积缓冲区

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def state(self) -> VoiceConversationState:
        return self._state

    def on_voice_input(self, callback: Callable[[str], None]) -> None:
        self._on_voice_input = callback

    def on_state_change(self, callback: Callable[[str], None]) -> None:
        self._on_state_change = callback

    async def start(self, continuous: bool = False) -> None:
        if self._running:
            logger.warning("VoiceRuntime already running")
            return

        self._continuous = continuous
        self._shutdown = False
        logger.info("Starting VoiceRuntime (continuous=%s)...", continuous)

        self._transport = LocalAudioTransport(self._config)
        self._vad = VADProcessor(threshold=self._config.vad_threshold)
        self._stt = STTProcessor(
            model_name=self._config.stt_model,
            language=self._config.stt_language,
            device=self._config.stt_device,
            compute_type=self._config.stt_compute_type,
        )
        self._cleanup = LLMCleanupProcessor(
            llm_fn=self._llm_fn,
            timeout=self._config.cleanup_timeout,
            min_length=self._config.cleanup_min_length,
        )

        self._pipeline = build_voice_pipeline(
            audio_source=self._transport,
            vad=self._vad,
            stt=self._stt,
            cleanup=self._cleanup,
            on_final_text=self._handle_final_text,
            hooks=self._hooks,
        )

        try:
            await self._run_pipeline()
        except Exception as exc:
            logger.error("Pipeline startup failed: %s", exc, exc_info=True)
            self._state = VoiceConversationState.IDLE
            self._hooks.fire("voice_state", state="error", error=str(exc))
            return

        self._running = True

        self._hooks.fire("voice_state", state="idle")
        if self._on_state_change:
            self._on_state_change("idle")

        logger.info("VoiceRuntime started")

    async def _run_pipeline(self) -> None:
        """启动 transport 和 pipeline 的实际运行。"""
        await self._transport.start()
        await self._pipeline.start()

    async def stop(self) -> None:
        if not self._running:
            return

        self._shutdown = True
        logger.info("Stopping VoiceRuntime...")

        # 取消空闲超时任务，避免 stop 后触发状态变更
        if self._idle_timeout_task is not None:
            self._idle_timeout_task.cancel()
            try:
                await self._idle_timeout_task
            except asyncio.CancelledError:
                pass
            self._idle_timeout_task = None

        try:
            if self._pipeline is not None:
                await self._pipeline.stop()
                self._pipeline = None
        except Exception as exc:
            logger.error("Error stopping pipeline: %s", exc)
        finally:
            await self._cleanup_audio()

            self._running = False
            self._state = VoiceConversationState.IDLE

            self._hooks.fire("voice_state", state="idle")
            if self._on_state_change:
                self._on_state_change("idle")

            logger.info("VoiceRuntime stopped")

    async def _cleanup_audio(self) -> None:
        """清理音频资源。"""
        if self._transport is not None:
            await self._transport.stop()
            self._transport = None

        self._vad = None
        self._stt = None
        self._cleanup = None

    def _handle_final_text(self, text: str) -> None:
        if self._shutdown:
            return
        self._state = VoiceConversationState.PROCESSING
        if self._on_voice_input:
            self._on_voice_input(text)

    def feed_response_text(self, text: str) -> None:
        """将 LLM 回复文本送入 TTS 合成。

        累积文本到缓冲区，在句子边界触发合成。
        """
        if self._shutdown or not self._running:
            return
        if not self._tts_client:
            return

        self._tts_buffer += text

        # 检查是否有完整句子可以合成
        import re
        # 在句号、问号、感叹号、换行处切分
        sentences = re.split(r'(?<=[。！？\n])', self._tts_buffer)
        if len(sentences) > 1:
            # 最后一段可能不完整，保留在缓冲区
            complete = "".join(sentences[:-1])
            self._tts_buffer = sentences[-1]
            if complete.strip():
                self._state = VoiceConversationState.SPEAKING
                self._hooks.fire("voice_state", state="speaking")
                asyncio.ensure_future(self._synthesize_and_speak(complete.strip()))

    async def _synthesize_and_speak(self, text: str) -> None:
        """合成文本并通过音频输出播放。"""
        try:
            async for chunk in self._tts_client.synthesize(text):
                if self._shutdown:
                    break
                # TODO: 将 PCM chunks 送入音频播放器
                logger.debug("TTS chunk: %d bytes", len(chunk))
            self._hooks.fire("voice_tts", chars=len(text))
        except Exception as exc:
            logger.error("TTS synthesis error: %s", exc)
            self._hooks.fire("voice_tts_error", error=str(exc))
        finally:
            # TTS 完成，触发状态转换
            self._on_tts_complete()

    def _on_tts_complete(self) -> None:
        """TTS 播放完成回调 — 决定下一步状态。"""
        if self._shutdown:
            return

        if self._continuous:
            # 连续模式：进入 SLEEPING，启动空闲超时
            self._state = VoiceConversationState.SLEEPING
            self._hooks.fire("voice_state", state="sleeping")
            if self._on_state_change:
                self._on_state_change("sleeping")
            self._start_idle_timeout()
        else:
            # 非连续模式：回到 IDLE
            self._state = VoiceConversationState.IDLE
            self._hooks.fire("voice_state", state="idle")
            if self._on_state_change:
                self._on_state_change("idle")

    def _start_idle_timeout(self) -> None:
        """启动空闲超时检测 — 连续模式下无语音则回到 IDLE。"""
        # 取消已有超时任务
        if self._idle_timeout_task is not None:
            self._idle_timeout_task.cancel()
            self._idle_timeout_task = None

        self._idle_timeout_task = asyncio.ensure_future(self._idle_timeout_loop())

    async def _idle_timeout_loop(self) -> None:
        """空闲超时检测循环。"""
        timeout = self._config.continuous_idle_timeout
        try:
            await asyncio.sleep(timeout)
            # 防御性检查：stop() 可能已设置 _shutdown
            if self._shutdown:
                return
            # 超时，回到 IDLE
            self._state = VoiceConversationState.IDLE
            self._hooks.fire("voice_state", state="idle")
            if self._on_state_change:
                self._on_state_change("idle")
            self._idle_timeout_task = None
        except asyncio.CancelledError:
            pass  # 被取消说明有新的语音输入

    def _handle_voice_detected(self) -> None:
        """检测到语音输入时取消超时并切换到 LISTENING。"""
        if self._idle_timeout_task is not None:
            self._idle_timeout_task.cancel()
            self._idle_timeout_task = None
        self._state = VoiceConversationState.LISTENING
        self._hooks.fire("voice_state", state="listening")
        if self._on_state_change:
            self._on_state_change("listening")
