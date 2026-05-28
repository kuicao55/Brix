"""VADProcessor — Silero VAD 语音活动检测。

检测音频流中的语音段起止。
语音开始时输出 VoiceStateFrame(state="speech_start")。
语音结束时输出 VoiceStateFrame(state="speech_end")。
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import torch

from capability.voice.config import VoiceConfig
from capability.voice.pipeline.frames import VoiceStateFrame

logger = logging.getLogger(__name__)


class VADProcessor:
    """Silero VAD 语音活动检测处理器。"""

    def __init__(
        self,
        threshold: float = 0.5,
        min_speech_chunks: int = 5,
        min_silence_chunks: int = 10,
    ) -> None:
        self._threshold = threshold
        self._min_speech_chunks = min_speech_chunks
        self._min_silence_chunks = min_silence_chunks
        self._model: Any = None
        self._is_speaking = False
        self._speech_chunk_count = 0
        self._silence_chunk_count = 0
        self._audio_buffer = bytearray()
        self._frames_collected: list = []

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    def _ensure_model(self) -> None:
        """懒加载 Silero VAD 模型。"""
        if self._model is None:
            try:
                from silero_vad import load_silero_vad
                self._model = load_silero_vad()
                logger.info("Silero VAD model loaded")
            except ImportError:
                logger.error("silero-vad not installed. Install with: pip install silero-vad")
                raise

    def _process_audio_chunk(self, audio_bytes: bytes) -> float:
        """处理单个音频 chunk，返回 VAD 置信度。"""
        self._ensure_model()
        audio_float = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(audio_float)
        confidence = self._model(audio_tensor, 16000)
        return float(confidence)

    def process_frame_sync(self, audio_bytes: bytes) -> list:
        """同步处理音频帧，返回产生的帧列表。"""
        self._ensure_model()
        audio_float = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(audio_float)
        confidence = float(self._model(audio_tensor, 16000))
        frames = []

        if confidence > self._threshold:
            self._silence_chunk_count = 0
            if not self._is_speaking:
                self._speech_chunk_count += 1
                if self._speech_chunk_count >= self._min_speech_chunks:
                    self._is_speaking = True
                    frames.append(VoiceStateFrame(state="speech_start"))
                    logger.debug("VAD: speech_start (confidence=%.3f)", confidence)
            if self._is_speaking:
                self._frames_collected.append(audio_bytes)
        else:
            self._speech_chunk_count = 0
            if self._is_speaking:
                self._silence_chunk_count += 1
                if self._silence_chunk_count >= self._min_silence_chunks:
                    self._is_speaking = False
                    frames.append(VoiceStateFrame(state="speech_end"))
                    logger.debug("VAD: speech_end (silence chunks=%d)", self._silence_chunk_count)

        return frames

    def get_collected_audio(self) -> bytes:
        """获取收集的语音音频数据并清空 buffer。"""
        audio = b"".join(self._frames_collected)
        self._frames_collected.clear()
        return audio

    def reset(self) -> None:
        """重置 VAD 状态。"""
        self._is_speaking = False
        self._speech_chunk_count = 0
        self._silence_chunk_count = 0
        self._frames_collected.clear()
