"""VoiceRuntimeImpl — 语音运行时实现。"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
import tempfile
import wave
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
        self._tts_cooldown_until: float = 0  # TTS 冷却期结束时间戳

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

    @property
    def tts_available(self) -> bool:
        return self._tts_client is not None

    def _is_speaking_or_cooldown(self) -> bool:
        """检查是否在 TTS 播放或冷却期内。"""
        import time
        # 检查 TTS 状态
        if self._state == VoiceConversationState.SPEAKING:
            return True
        # 检查 AudioPlayer 是否正在播放（包括缓冲区中的音频）
        if self._audio_player is not None and self._audio_player.is_playing:
            return True
        # 检查冷却期
        if time.time() < self._tts_cooldown_until:
            return True
        return False

    @property
    def tts_playback_mode(self) -> str:
        """当前 TTS 播放模式：pyaudio / afplay_pcm / system_say / none。"""
        if self._tts_client is None:
            return "none"
        if self._audio_player is not None and self._audio_player.is_active:
            return "pyaudio"
        if self._pcm_playback_available():
            return "afplay_pcm"
        if self._system_tts_available():
            return "system_say"
        return "none"

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
            interim_model_name=self._config.stt_interim_model,
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
            is_speaking=self._is_speaking_or_cooldown,
            cleanup_enabled=self._config.cleanup_enabled,
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
        elif vad_state == "idle" and self._state != VoiceConversationState.IDLE:
            # STT 超时或错误 → 重置回 IDLE
            self._state = VoiceConversationState.IDLE
            if self._on_state_change:
                self._on_state_change("idle")

    @staticmethod
    def _sanitize_for_tts(text: str) -> str:
        """清理文本供 TTS 使用 — 去除 emoji、markdown 等特殊字符。"""
        import re

        # 去除 emoji（保留中文、英文、数字、基本标点）
        # 使用 emoji 库或简化的 emoji 检测
        # 注意：不要使用过于宽泛的 Unicode 范围，否则会误删中文字符

        # 常见 emoji 的 Unicode 范围（精确匹配，避免误删中文）
        emoji_pattern = re.compile(
            r'[\U0001F600-\U0001F64F'  # emoticons (😀-🙏)
            r'\U0001F300-\U0001F5FF'  # symbols & pictographs (🌀-🗿)
            r'\U0001F680-\U0001F6FF'  # transport & map (🚀-➿)
            r'\U0001F900-\U0001F9FF'  # supplemental symbols (🤀-🧿)
            r'\U0001FA00-\U0001FA6F'  # chess symbols
            r'\U0001FA70-\U0001FAFF'  # symbols extended-A
            r'\U00002600-\U000026FF'  # misc symbols (☀-⛿)
            r'\U00002700-\U000027BF'  # dingbats (✀-➿)
            r'\U0000FE00-\U0000FE0F'  # variation selectors
            r'\U0000200D'  # zero width joiner
            r'\U00002B50'  # star
            r'\U0000231A-\U0000231B'  # watch, hourglass
            r'\U000023E9-\U000023F3'  # media controls
            r'\U000023F8-\U000023FA'  # media controls
            r'\U000025AA-\U000025AB'  # squares
            r'\U000025B6'  # play button
            r'\U000025C0'  # reverse button
            r'\U000025FB-\U000025FE'  # squares
            r'\U00002614-\U00002615'  # umbrella, coffee
            r'\U00002648-\U00002653'  # zodiac
            r'\U0000267F'  # wheelchair
            r'\U00002693'  # anchor
            r'\U000026A1'  # lightning
            r'\U000026AA-\U000026AB'  # circles
            r'\U000026BD-\U000026BE'  # soccer, baseball
            r'\U000026C4-\U000026C5'  # snowman, sun
            r'\U000026CE'  # ophiuchus
            r'\U000026D4'  # no entry
            r'\U000026EA'  # church
            r'\U000026F2-\U000026F3'  # fountain, golf
            r'\U000026F5'  # sailboat
            r'\U000026FA'  # tent
            r'\U000026FD'  # fuel pump
            r'\U00002702'  # scissors
            r'\U00002705'  # check mark
            r'\U00002708-\U0000270D'  # various
            r'\U0000270F'  # pencil
            r'\U00002712'  # black nib
            r'\U00002714'  # check mark
            r'\U00002716'  # multiplication
            r'\U0000271D'  # latin cross
            r'\U00002721'  # star of david
            r'\U00002728'  # sparkles
            r'\U00002733-\U00002734'  # eight spoked asterisk
            r'\U00002744'  # snowflake
            r'\U00002747'  # sparkle
            r'\U0000274C'  # cross mark
            r'\U0000274E'  # cross mark
            r'\U00002753-\U00002755'  # question marks
            r'\U00002757'  # exclamation
            r'\U00002763-\U00002764'  # heart exclamation, heart
            r'\U00002795-\U00002797'  # plus, minus, divide
            r'\U000027A1'  # arrow
            r'\U000027B0'  # curly loop
            r']+',
            re.UNICODE
        )
        text = emoji_pattern.sub('', text)

        # 去除 markdown 标记
        text = re.sub(r'[*_`#~\[\]()]+', '', text)
        # 去除多余空白
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def _is_tts_candidate(text: str) -> bool:
        """是否值得送入 TTS，过滤掉无意义短片段（如 '...'、'bug'）。"""
        import re

        if not text:
            return False
        if not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", text):
            return False
        if re.fullmatch(r"[.\-_,，。！？!?;；:：\s]+", text):
            return False

        has_cjk = re.search(r"[\u4e00-\u9fff]", text) is not None
        if has_cjk:
            return len(text) >= 2

        # 非中文短词（常见于代码流）不读，避免触发 418
        return len(text) >= 8

    def flush_tts(self) -> None:
        """Flush TTS buffer 中剩余文本（流结束时调用）。"""
        logger.info("TTS flush_tts called: shutdown=%s, running=%s, tts_client=%s, buffer='%s'",
                    self._shutdown, self._running,
                    type(self._tts_client).__name__ if self._tts_client else "None",
                    self._tts_buffer[:50] if self._tts_buffer else "")

        if self._shutdown or not self._running or not self._tts_client:
            logger.warning("TTS flush_tts skipped: shutdown=%s, running=%s, tts_client=%s",
                          self._shutdown, self._running, self._tts_client is not None)
            return

        if self._tts_buffer.strip():
            sanitized = self._sanitize_for_tts(self._tts_buffer.strip())
            self._tts_buffer = ""
            logger.info("TTS flush_tts: sanitized text='%s' (len=%d)", sanitized[:50], len(sanitized))

            if sanitized and self._is_tts_candidate(sanitized):
                logger.info("TTS flush_tts: triggering synthesis")
                self._hooks.fire("voice_tts_queue", text=sanitized[:80], source="flush")
                self._state = VoiceConversationState.SPEAKING
                self._hooks.fire("voice_state", state="speaking")
                asyncio.ensure_future(self._synthesize_and_speak(sanitized))
            else:
                logger.info("TTS flush_tts: text skipped (candidate=%s)", self._is_tts_candidate(sanitized) if sanitized else "empty")
                if sanitized:
                    self._hooks.fire("voice_tts_skip", text=sanitized[:80], source="flush")
        else:
            logger.info("TTS flush_tts: buffer empty")

    def feed_response_text(self, text: str) -> None:
        """将 LLM 回复文本送入 TTS 合成。

        累积文本到缓冲区，统一在 flush_tts 时一次性合成。
        """
        if self._shutdown or not self._running:
            return
        if not self._tts_client:
            return
        self._tts_buffer += text

    async def _synthesize_and_speak(self, text: str) -> None:
        """合成文本并通过音频输出播放。"""
        logger.info("TTS: Starting synthesis for text: '%s...' (%d chars)", text[:50], len(text))
        try:
            backend = "unknown"
            if self._tts_client is None:
                logger.warning("TTS: No TTS client available, trying system TTS")
                if await self._speak_with_system_tts(text):
                    self._hooks.fire(
                        "voice_tts",
                        chars=len(text),
                        chunks=0,
                        bytes=0,
                        backend="system_say",
                    )
                    logger.info("TTS: System TTS succeeded")
                    return
                logger.warning("TTS: System TTS also failed")
                self._hooks.fire(
                    "voice_tts_error",
                    error="tts_playback_unavailable",
                    backend="none",
                )
                return

            logger.info("TTS: Using TTS client: %s", type(self._tts_client).__name__)
            logger.info("TTS: Audio player active: %s", self._audio_player is not None and self._audio_player.is_active)

            chunk_count = 0
            byte_count = 0
            pcm_parts: list[bytes] = []

            async def _tracked_chunks():
                nonlocal chunk_count, byte_count
                logger.info("TTS: Starting synthesis stream...")
                async for chunk in self._tts_client.synthesize(text):
                    if chunk:
                        chunk_count += 1
                        byte_count += len(chunk)
                        if chunk_count <= 3:  # 只记录前3个chunk
                            logger.info("TTS: Received chunk %d, size=%d bytes", chunk_count, len(chunk))
                        if self._audio_player is None or not self._audio_player.is_active:
                            pcm_parts.append(chunk)
                        yield chunk
                logger.info("TTS: Synthesis stream completed, total chunks=%d, bytes=%d", chunk_count, byte_count)

            if self._audio_player is not None and self._audio_player.is_active:
                backend = "pyaudio"
                logger.info("TTS: Using PyAudio backend for playback")
                # 流式合成并播放
                await self._audio_player.play_chunks(
                    _tracked_chunks()
                )
                logger.info("TTS: PyAudio playback completed")
            else:
                backend = "afplay_pcm"
                logger.info("TTS: PyAudio not available, using afplay fallback")
                # 无 PyAudio：仍调用 CosyVoice，再用 afplay 播放 PCM
                async for _ in _tracked_chunks():
                    if self._shutdown:
                        logger.info("TTS: Shutdown during synthesis")
                        break
                if chunk_count > 0:
                    logger.info("TTS: Playing %d bytes PCM with afplay", byte_count)
                    pcm = b"".join(pcm_parts)
                    played = await self._play_pcm_with_afplay(pcm)
                    if not played:
                        logger.warning("TTS: afplay failed, falling back to system TTS")
                        if not await self._speak_with_system_tts(text):
                            self._hooks.fire(
                                "voice_tts_error",
                                error="tts_playback_unavailable",
                                backend="none",
                            )
                            return
                        backend = "system_say_fallback"
                    else:
                        logger.info("TTS: afplay succeeded")
                else:
                    logger.warning("TTS: No audio chunks produced")

            if chunk_count == 0:
                logger.warning("TTS produced no audio: '%s'", text[:60])
                self._hooks.fire(
                    "voice_tts_error",
                    error="tts_empty_audio",
                    backend=backend,
                )
                return

            logger.info("TTS: Success - backend=%s, chunks=%d, bytes=%d", backend, chunk_count, byte_count)
            self._hooks.fire(
                "voice_tts",
                chars=len(text),
                chunks=chunk_count,
                bytes=byte_count,
                backend=backend,
            )
        except Exception as exc:
            logger.error("TTS synthesis error: %s", exc, exc_info=True)
            self._hooks.fire("voice_tts_error", error=str(exc), backend="exception")
        finally:
            # TTS 完成，触发状态转换
            logger.info("TTS: Synthesis completed, calling _on_tts_complete")
            self._on_tts_complete()

    @staticmethod
    def _pcm_playback_available() -> bool:
        return sys.platform == "darwin" and shutil.which("afplay") is not None

    async def _play_pcm_with_afplay(self, pcm_data: bytes) -> bool:
        """用 afplay 播放 CosyVoice PCM（macOS，无 PyAudio 时）。"""
        if not pcm_data or not self._pcm_playback_available():
            return False

        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="brix_tts_", suffix=".wav", delete=False) as f:
                wav_path = f.name

            with wave.open(wav_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # int16
                wav_file.setframerate(self._config.tts_sample_rate)
                wav_file.writeframes(pcm_data)

            proc = await asyncio.create_subprocess_exec(
                "afplay",
                wav_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            rc = await proc.wait()
            return rc == 0
        except Exception as exc:
            logger.warning("afplay PCM failed: %s", exc)
            return False
        finally:
            if wav_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

    @staticmethod
    def _system_tts_available() -> bool:
        return sys.platform == "darwin" and shutil.which("say") is not None

    async def _speak_with_system_tts(self, text: str) -> bool:
        """macOS 系统语音兜底。"""
        if not self._system_tts_available():
            return False
        if not text.strip():
            return False

        voice = "Ting-Ting" if re.search(r"[\u4e00-\u9fff]", text) else "Samantha"
        try:
            proc = await asyncio.create_subprocess_exec(
                "say",
                "-v",
                voice,
                text,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            rc = await proc.wait()
            return rc == 0
        except Exception as exc:
            logger.warning("System TTS failed: %s", exc)
            return False

    def _on_tts_complete(self) -> None:
        """TTS 合成完成回调 — 等待音频真正播放完成后恢复监听。"""
        if self._shutdown:
            return

        # 等待音频真正播放完成
        asyncio.ensure_future(self._wait_for_playback_finish())

    async def _wait_for_playback_finish(self) -> None:
        """等待音频真正播放完成后恢复监听。"""
        import time

        # 1. 等待 AudioPlayer 播放完成（包括缓冲区中的音频）
        if self._audio_player is not None:
            logger.info("TTS: Waiting for AudioPlayer to finish playback...")
            while self._audio_player.is_playing:
                await asyncio.sleep(0.05)  # 50ms 轮询
                if self._shutdown:
                    return
            logger.info("TTS: AudioPlayer playback finished")

        # 2. 额外冷却期：防止扬声器余音被麦克风捕获
        cooldown_ms = self._config.tts_cooldown_ms if hasattr(self._config, 'tts_cooldown_ms') else 500
        logger.info("TTS: Cooling down for %dms to prevent echo", cooldown_ms)
        self._tts_cooldown_until = time.time() + (cooldown_ms / 1000)
        await asyncio.sleep(cooldown_ms / 1000)
        self._tts_cooldown_until = 0

        if self._shutdown:
            return

        # 3. 恢复监听
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
