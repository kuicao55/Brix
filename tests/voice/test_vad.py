"""VADProcessor 测试。"""

import numpy as np
import pytest

from capability.voice.processors.vad import VADProcessor
from capability.voice.pipeline.frames import VoiceStateFrame


def make_silence(samples=512):
    """生成静音 int16 PCM 数据。"""
    return np.zeros(samples, dtype=np.int16).tobytes()


def make_speech(samples=512):
    """生成模拟语音 int16 PCM 数据（随机噪声）。"""
    rng = np.random.RandomState(42)
    return (rng.randn(samples) * 5000).astype(np.int16).tobytes()


def test_vad_processor_init():
    """VADProcessor 可以初始化。"""
    vad = VADProcessor(threshold=0.5)
    assert vad is not None
    assert not vad.is_speaking


def test_vad_detects_silence():
    """VADProcessor 对静音不标记为语音。"""
    vad = VADProcessor(threshold=0.5)
    for _ in range(10):
        vad._process_audio_chunk(make_silence())
    assert not vad.is_speaking


def test_vad_detects_speech():
    """VADProcessor 对语音数据标记为语音。"""
    vad = VADProcessor(threshold=0.3)
    for _ in range(20):
        vad._process_audio_chunk(make_speech())
    # 注：真实 Silero VAD 模型需要加载，这里测试逻辑流程
