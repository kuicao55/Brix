"""语音模块配置测试。"""

from capability.voice.config import VoiceConfig


def test_voice_config_defaults():
    """VoiceConfig 有合理的默认值。"""
    cfg = VoiceConfig()
    assert cfg.sample_rate == 16000
    assert cfg.channels == 1
    assert cfg.chunk_samples == 512  # Silero VAD 对齐
    assert cfg.vad_threshold == 0.5
    assert cfg.stt_model == "small"
    assert cfg.stt_language == "zh"


def test_voice_config_from_dict():
    """VoiceConfig 可以从 dict 构造。"""
    cfg = VoiceConfig.from_dict({
        "voice": {
            "sample_rate": 44100,
            "stt_model": "large-v3",
        }
    })
    assert cfg.sample_rate == 44100
    assert cfg.stt_model == "large-v3"
    assert cfg.vad_threshold == 0.5  # 未指定的用默认值
