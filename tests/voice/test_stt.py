"""STTProcessor 测试。"""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from capability.voice.processors.stt import STTProcessor
from capability.voice.pipeline.frames import VoiceStateFrame, CleanedTextFrame


def make_audio_bytes(duration_ms=1000, sample_rate=16000):
    """生成模拟音频 int16 PCM 数据。"""
    samples = int(sample_rate * duration_ms / 1000)
    rng = np.random.RandomState(42)
    return (rng.randn(samples) * 5000).astype(np.int16).tobytes()


def test_stt_processor_init():
    """STTProcessor 可以初始化。"""
    stt = STTProcessor(model_name="small", language="zh", device="cpu")
    assert stt is not None
    assert stt._language == "zh"


def test_stt_transcribes_audio():
    """STTProcessor 对音频数据进行转录。"""
    stt = STTProcessor(model_name="small", language="zh", device="cpu")

    # Mock _transcribe_audio 避免实际子进程调用
    with patch.object(stt, "_transcribe_audio", return_value="你好世界"):
        audio = make_audio_bytes(1000)
        result_frames = stt.transcribe_sync(audio)

    assert len(result_frames) == 1
    assert result_frames[0].text == "你好世界"


def test_stt_empty_audio():
    """STTProcessor 对空音频不输出帧。"""
    stt = STTProcessor(model_name="small", language="zh", device="cpu")

    with patch.object(stt, "_transcribe_audio", return_value=""):
        result_frames = stt.transcribe_sync(b"")
    assert len(result_frames) == 0


def test_stt_voice_end_triggers_transcribe():
    """收到 speech_end 帧时触发转录。"""
    stt = STTProcessor(model_name="small", language="zh", device="cpu")
    stt._audio_buffer = make_audio_bytes(500)

    with patch.object(stt, "_transcribe_audio", return_value="测试文本"):
        frames = stt.process_frame_sync(VoiceStateFrame(state="speech_end"))

    assert len(frames) == 1
    assert frames[0].text == "测试文本"
    assert stt._audio_buffer == bytearray()


def test_stt_audio_buffering():
    """音频帧被正确缓冲。"""
    stt = STTProcessor(model_name="small", language="zh", device="cpu")

    audio = make_audio_bytes(100)
    frame = type("AudioFrame", (), {"audio": audio})()
    stt.process_frame_sync(frame)

    assert len(stt._audio_buffer) == len(audio)


def test_stt_interim_requires_minimum_audio():
    """Interim 转录需要最少 0.5s 音频。"""
    stt = STTProcessor(model_name="small", language="zh", device="cpu")

    # 太短的音频返回空
    short_audio = make_audio_bytes(100)  # 100ms
    assert stt.transcribe_interim(short_audio) == ""

    # 足够长的音频调用 _transcribe_audio
    long_audio = make_audio_bytes(1000)  # 1s
    with patch.object(stt, "_transcribe_audio", return_value="测试"):
        assert stt.transcribe_interim(long_audio) == "测试"
