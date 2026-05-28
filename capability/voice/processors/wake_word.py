"""WakeWordProcessor — openWakeWord 唤醒词检测。

未唤醒时丢弃音频帧。唤醒后透传。
唤醒词检测到后输出 VoiceStateFrame(state="wake_detected")。
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class WakeWordProcessor:
    """openWakeWord 唤醒词检测处理器。"""

    def __init__(
        self,
        threshold: float = 0.5,
        model_name: str = "hey_brix",
        silence_limit_chunks: int = 300,  # 约 15 秒 @ 512 samples/16kHz
    ) -> None:
        self._threshold = threshold
        self._model_name = model_name
        self._silence_limit = silence_limit_chunks
        self._model: Any = None
        self._awake = False
        self._silence_count = 0

    @property
    def is_awake(self) -> bool:
        return self._awake

    def _ensure_model(self) -> None:
        """懒加载 openWakeWord 模型。"""
        if self._model is None:
            try:
                from openwakeword.model import Model
                self._model = Model(wakeword_models=[self._model_name])
                logger.info("openWakeWord model loaded: %s", self._model_name)
            except ImportError:
                logger.error("openwakeword not installed. Install with: pip install openwakeword")
                raise

    def process_audio_sync(self, audio_bytes: bytes) -> bytes | None:
        """同步处理音频，返回音频（唤醒后）或 None（未唤醒）。用于测试。"""
        if self._awake:
            return audio_bytes
        return None

    def detect_sync(self, audio_bytes: bytes) -> bool:
        """同步检测唤醒词，返回是否唤醒。用于测试。"""
        self._ensure_model()
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        prediction = self._model.predict(audio_int16)
        confidence = prediction.get(self._model_name, 0)
        if confidence > self._threshold:
            self._awake = True
            self._silence_count = 0
            return True
        return False

    def process_frame_sync(self, audio_bytes: bytes) -> list:
        """同步处理帧，返回产生的帧列表。用于测试。"""
        from capability.voice.pipeline.frames import VoiceStateFrame

        frames = []
        if self._awake:
            # 已唤醒：透传音频，检测是否该休眠
            if audio_bytes:
                # 有音频 → 重置静默计数
                self._silence_count = 0
            else:
                # 静默 → 递增计数
                self._silence_count += 1
            if self._silence_count >= self._silence_limit:
                self._awake = False
                frames.append(VoiceStateFrame(state="sleep"))
                logger.debug("WakeWord: auto-sleep (silence timeout)")
        else:
            # 未唤醒：检测唤醒词
            if self.detect_sync(audio_bytes):
                frames.append(VoiceStateFrame(state="wake_detected"))
                logger.debug("WakeWord: wake_detected")

        return frames

    def sleep(self) -> None:
        """手动休眠。"""
        self._awake = False
        self._silence_count = 0

    def reset(self) -> None:
        """重置状态。"""
        self.sleep()
