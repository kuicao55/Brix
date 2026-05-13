"""ResampleProcessor 测试。"""

import numpy as np
import pytest

from capability.voice.processors.resample import ResampleProcessor


def test_resample_24k_to_48k():
    """ResampleProcessor 将 24kHz 重采样到 48kHz。"""
    proc = ResampleProcessor(src_rate=24000, dst_rate=48000)

    # 生成 24kHz 的 100ms 音频
    samples_24k = int(24000 * 0.1)
    audio_24k = np.sin(np.linspace(0, 2 * np.pi * 440, samples_24k))
    audio_24k_int16 = (audio_24k * 32767).astype(np.int16).tobytes()

    result = proc.resample(audio_24k_int16, src_rate=24000)

    # 结果应该是 48kHz 的 100ms 音频
    result_array = np.frombuffer(result, dtype=np.int16)
    assert len(result_array) == samples_24k * 2  # 48000 samples for 100ms


def test_resample_preserves_amplitude():
    """ResampleProcessor 保持音频幅度。"""
    proc = ResampleProcessor(src_rate=24000, dst_rate=48000)

    # 生成恒定幅度的音频
    samples = 2400  # 100ms @ 24kHz
    audio = np.full(samples, 16000, dtype=np.int16).tobytes()

    result = proc.resample(audio, src_rate=24000)
    result_array = np.frombuffer(result, dtype=np.int16)

    # 幅度应大致保持
    assert np.abs(np.mean(result_array) - 16000) < 100


def test_resample_same_rate_passthrough():
    """ResampleProcessor 相同采样率时直接透传。"""
    proc = ResampleProcessor(src_rate=48000, dst_rate=48000)

    audio = np.zeros(4800, dtype=np.int16).tobytes()
    result = proc.resample(audio, src_rate=48000)

    assert result == audio
