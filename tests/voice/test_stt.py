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
    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "你好世界"
    mock_info = MagicMock()
    mock_info.language = "zh"
    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    stt = STTProcessor(model_name="small", language="zh", device="cpu")
    stt._model = mock_model

    audio = make_audio_bytes(1000)
    result_frames = stt.transcribe_sync(audio)

    assert len(result_frames) == 1
    assert result_frames[0].text == "你好世界"
    mock_model.transcribe.assert_called_once()


def test_stt_empty_audio():
    """STTProcessor 对空转录结果不输出帧。"""
    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = ""
    mock_info = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    stt = STTProcessor(model_name="small", language="zh", device="cpu")
    stt._model = mock_model

    result_frames = stt.transcribe_sync(b"")
    assert len(result_frames) == 0


def test_stt_voice_end_triggers_transcribe():
    """收到 speech_end 帧时触发转录。"""
    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "测试文本"
    mock_info = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    stt = STTProcessor(model_name="small", language="zh", device="cpu")
    stt._model = mock_model
    stt._audio_buffer = make_audio_bytes(500)

    frames = stt.process_frame_sync(VoiceStateFrame(state="speech_end"))
    assert len(frames) == 1
    assert frames[0].text == "测试文本"
    assert stt._audio_buffer == b""
