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
    ) -> None:
        self._config = config
        self._hooks = hooks
        self._llm_fn = llm_fn
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
