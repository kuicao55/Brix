"""STTProcessor — faster-whisper 语音识别。

语音结束后整段转录（非实时流式），中文效果更好。
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from capability.voice.config import VoiceConfig
from capability.voice.pipeline.frames import CleanedTextFrame, VoiceStateFrame

logger = logging.getLogger(__name__)


class STTProcessor:
    """faster-whisper 语音识别处理器。"""

    def __init__(
        self,
        model_name: str = "small",
        language: str = "zh",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self._model_name = model_name
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._model: Any = None
        self._audio_buffer = bytearray()

    def _ensure_model(self) -> None:
        """懒加载 faster-whisper 模型。"""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self._model_name,
                    device=self._device,
                    compute_type=self._compute_type,
                )
                logger.info(
                    "faster-whisper model loaded: %s (%s/%s)",
                    self._model_name,
                    self._device,
                    self._compute_type,
                )
            except ImportError:
                logger.error(
                    "faster-whisper not installed. Install with: pip install faster-whisper"
                )
                raise

    def _transcribe_audio(self, audio_bytes: bytes) -> str:
        """转录音频数据为文本。"""
        if not audio_bytes:
            return ""

        audio_array = (
            np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        )
        segments, info = self._model.transcribe(
            audio_array,
            language=self._language,
            beam_size=5,
            vad_filter=False,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        logger.debug("STT result: %s (lang=%s)", text[:50], info.language)
        return text

    def transcribe_sync(self, audio_bytes: bytes) -> list[CleanedTextFrame]:
        """同步转录，返回 CleanedTextFrame 列表。用于测试。"""
        self._ensure_model()
        text = self._transcribe_audio(audio_bytes)
        if text:
            return [CleanedTextFrame(text=text, raw_text=text)]
        return []

    def process_frame_sync(self, frame: Any) -> list:
        """同步处理帧，返回产生的帧列表。用于测试。"""
        if isinstance(frame, VoiceStateFrame) and frame.state == "speech_end":
            audio = bytes(self._audio_buffer)
            self._audio_buffer = bytearray()
            text = self._transcribe_audio(audio)
            if text:
                return [CleanedTextFrame(text=text, raw_text=text)]
            return []
        elif hasattr(frame, "audio"):
            self._audio_buffer.extend(frame.audio)
        return []

    def reset(self) -> None:
        """重置 STT 状态。"""
        self._audio_buffer.clear()
