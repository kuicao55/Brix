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
    assert cfg.stt_interim_model == "tiny"
    assert cfg.stt_language == "zh"
    assert cfg.input_enabled is True
    assert cfg.output_enabled is True


def test_voice_config_from_dict():
    """VoiceConfig 可以从 dict 构造。"""
    cfg = VoiceConfig.from_dict({
        "voice": {
            "sample_rate": 44100,
            "stt_model": "large-v3",
            "stt_interim_model": "small",
        }
    })
    assert cfg.sample_rate == 44100
    assert cfg.stt_model == "large-v3"
    assert cfg.stt_interim_model == "small"
    assert cfg.vad_threshold == 0.5  # 未指定的用默认值


def test_voice_config_from_dict_input_output_flags():
    """VoiceConfig 可以从 dict 设置 input_enabled / output_enabled。"""
    cfg = VoiceConfig.from_dict({
        "voice": {
            "input_enabled": False,
            "output_enabled": True,
        }
    })
    assert cfg.input_enabled is False
    assert cfg.output_enabled is True


def test_voice_config_input_output_defaults():
    """VoiceConfig 默认 input_enabled=True, output_enabled=True。"""
    cfg = VoiceConfig()
    assert cfg.input_enabled is True
    assert cfg.output_enabled is True
