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
from capability.voice.transport.audio_player import AudioPlayer
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
        self._on_interim_text: Optional[Callable[[str], None]] = None

        self._transport: Optional[LocalAudioTransport] = None
        self._audio_player: Optional[AudioPlayer] = None
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

    def on_interim_text(self, callback: Callable[[str], None]) -> None:
        self._on_interim_text = callback

    async def start(self, continuous: bool = False) -> None:
        if self._running:
            logger.warning("VoiceRuntime already running")
            return

        self._continuous = continuous
        self._shutdown = False
        logger.info("Starting VoiceRuntime (continuous=%s)...", continuous)

        self._transport = LocalAudioTransport(self._config)
        self._audio_player = AudioPlayer(
            sample_rate=self._config.tts_sample_rate,
        )
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
            on_interim_text=self._handle_interim_text,
            hooks=self._hooks,
            is_speaking=lambda: self._state == VoiceConversationState.SPEAKING,
        )

        # 监听 pipeline 的 VAD 事件，更新状态并通知 CLI
        self._hooks.register("voice_state", self._on_pipeline_voice_state)

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
        self._stt.start()  # 启动 STT 持久化子进程
        await self._transport.start()
        if self._audio_player is not None:
            await self._audio_player.start()
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
        if self._audio_player is not None:
            await self._audio_player.stop()
            self._audio_player = None

        if self._transport is not None:
            await self._transport.stop()
            self._transport = None

        self._vad = None
        if self._stt is not None:
            self._stt.stop()
        self._stt = None
        self._cleanup = None

    def _handle_final_text(self, text: str) -> None:
        if self._shutdown:
            return
        self._state = VoiceConversationState.PROCESSING
        if self._on_voice_input:
            self._on_voice_input(text)

    def _handle_interim_text(self, text: str) -> None:
        if self._shutdown:
            return
        if self._on_interim_text:
            self._on_interim_text(text)

    def _on_pipeline_voice_state(self, event: Any) -> None:
        """Pipeline VAD 事件处理 — 更新状态并通知 CLI。"""
        if self._shutdown:
            return
        vad_state = event.data.get("state", "")
        if vad_state == "speech_start" and self._state != VoiceConversationState.LISTENING:
            self._state = VoiceConversationState.LISTENING
            if self._on_state_change:
                self._on_state_change("listening")
        elif vad_state == "speech_end" and self._state == VoiceConversationState.LISTENING:
            self._state = VoiceConversationState.PROCESSING
            if self._on_state_change:
                self._on_state_change("processing")

    @staticmethod
    def _sanitize_for_tts(text: str) -> str:
        """清理文本供 TTS 使用 — 去除 emoji、markdown 等特殊字符。"""
        import re

        # 去除 emoji（保留中文、英文、数字、基本标点）
        text = re.sub(
            r'[\U0001F600-\U0001F64F'  # emoticons
            r'\U0001F300-\U0001F5FF'  # symbols & pictographs
            r'\U0001F680-\U0001F6FF'  # transport & map
            r'\U0001F1E0-\U0001F1FF'  # flags
            r'\U00002702-\U000027B0'
            r'\U000024C2-\U0001F251'
            r'\U0001f926-\U0001f937'
            r'\U00010000-\U0010ffff'
            r'\u2600-\u26FF'
            r'\u2700-\u27BF'
            r'\u200d'
            r'\ufe0f]+',
            '',
            text,
        )
        # 去除 markdown 标记
        text = re.sub(r'[*_`#~\[\]()]+', '', text)
        # 去除多余空白
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def flush_tts(self) -> None:
        """Flush TTS buffer 中剩余文本（流结束时调用）。"""
        if self._shutdown or not self._running or not self._tts_client:
            return
        if self._tts_buffer.strip():
            sanitized = self._sanitize_for_tts(self._tts_buffer.strip())
            self._tts_buffer = ""
            if sanitized:
                self._state = VoiceConversationState.SPEAKING
                self._hooks.fire("voice_state", state="speaking")
                asyncio.ensure_future(self._synthesize_and_speak(sanitized))

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
        # 在句号、问号、感叹号、换行处切分；逗号处仅当累积文本较长时切分
        sentences = re.split(r'(?<=[。！？\n])', self._tts_buffer)
        if len(sentences) > 1:
            complete = "".join(sentences[:-1])
            self._tts_buffer = sentences[-1]
        elif len(self._tts_buffer) > 30:
            # 无句号但累积较长时，在逗号处切分
            clauses = re.split(r'(?<=[，,])', self._tts_buffer)
            if len(clauses) > 1:
                complete = "".join(clauses[:-1])
                self._tts_buffer = clauses[-1]
            else:
                complete = ""
        else:
            complete = ""

        if complete.strip():
            sanitized = self._sanitize_for_tts(complete.strip())
            if sanitized:
                self._state = VoiceConversationState.SPEAKING
                self._hooks.fire("voice_state", state="speaking")
                asyncio.ensure_future(self._synthesize_and_speak(sanitized))

    async def _synthesize_and_speak(self, text: str) -> None:
        """合成文本并通过音频输出播放。"""
        try:
            if self._audio_player is not None and self._audio_player.is_active:
                # 流式合成并播放
                await self._audio_player.play_chunks(
                    self._tts_client.synthesize(text)
                )
            else:
                # 无播放器，仅合成（调试用）
                async for chunk in self._tts_client.synthesize(text):
                    if self._shutdown:
                        break
                    logger.debug("TTS chunk: %d bytes (no player)", len(chunk))
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
