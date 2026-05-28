"""ResampleProcessor — 音频重采样。

使用 scipy.signal.resample_poly 做高质量重采样。
在 asyncio event loop 中运行，不阻塞 PyAudio I/O 线程。
"""

from __future__ import annotations

import logging
from math import gcd

import numpy as np

logger = logging.getLogger(__name__)


class ResampleProcessor:
    """音频重采样处理器。"""

    def __init__(self, src_rate: int = 24000, dst_rate: int = 48000) -> None:
        self._src_rate = src_rate
        self._dst_rate = dst_rate

        if src_rate == dst_rate:
            self._up = 1
            self._down = 1
        else:
            g = gcd(dst_rate, src_rate)
            self._up = dst_rate // g
            self._down = src_rate // g

        self._needs_resample = (src_rate != dst_rate)
        logger.debug("ResampleProcessor: %dHz -> %dHz (up=%d, down=%d)",
                      src_rate, dst_rate, self._up, self._down)

    def resample(self, audio_bytes: bytes, src_rate: int | None = None) -> bytes:
        """重采样音频数据。

        Args:
            audio_bytes: int16 PCM 音频数据
            src_rate: 源采样率（覆盖构造函数的值）

        Returns:
            重采样后的 int16 PCM 音频数据
        """
        if not self._needs_resample:
            return audio_bytes

        from scipy.signal import resample_poly

        samples = np.frombuffer(audio_bytes, dtype=np.int16)
        if len(samples) == 0:
            return audio_bytes

        resampled = resample_poly(samples, self._up, self._down)
        resampled_int16 = np.clip(resampled, -32768, 32767).astype(np.int16)
        return resampled_int16.tobytes()

    @property
    def output_sample_rate(self) -> int:
        """输出采样率。"""
        return self._dst_rate
