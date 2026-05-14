"""语音配置与 Brix 配置系统集成测试。"""

from capability.voice.config import VoiceConfig


def test_voice_config_from_brix_config():
    """VoiceConfig 从 Brix 配置 dict 中读取 voice 节。"""
    brix_config = {
        "voice": {
            "enabled": True,
            "sample_rate": 44100,
            "stt_model": "large-v3",
            "cleanup_model": "qwen-turbo",
        },
        "routing": {"default_model": "openai/gpt-4o"},
    }

    cfg = VoiceConfig.from_dict(brix_config)
    assert cfg.sample_rate == 44100
    assert cfg.stt_model == "large-v3"
    assert cfg.cleanup_model == "qwen-turbo"
    # 未指定的用默认值
    assert cfg.vad_threshold == 0.5
    assert cfg.stt_language == "zh"


def test_voice_config_missing_voice_section():
    """VoiceConfig 在无 voice 节时使用默认值。"""
    brix_config = {"routing": {"default_model": "openai/gpt-4o"}}
    cfg = VoiceConfig.from_dict(brix_config)
    assert cfg.sample_rate == 16000
    assert cfg.stt_model == "small"


def test_voice_config_partial_override():
    """VoiceConfig 只覆盖指定字段，其余保持默认。"""
    brix_config = {
        "voice": {
            "vad_threshold": 0.7,
            "continuous_idle_timeout": 15.0,
        }
    }
    cfg = VoiceConfig.from_dict(brix_config)
    assert cfg.vad_threshold == 0.7
    assert cfg.continuous_idle_timeout == 15.0
    # 默认值不变
    assert cfg.sample_rate == 16000
    assert cfg.wake_threshold == 0.5


def test_voice_config_ignores_unknown_keys():
    """VoiceConfig 忽略未知配置键。"""
    brix_config = {
        "voice": {
            "sample_rate": 22050,
            "unknown_key": "should_be_ignored",
        }
    }
    cfg = VoiceConfig.from_dict(brix_config)
    assert cfg.sample_rate == 22050
    assert not hasattr(cfg, "unknown_key")


def test_voice_config_all_defaults():
    """VoiceConfig 默认值完整。"""
    cfg = VoiceConfig()
    assert cfg.sample_rate == 16000
    assert cfg.channels == 1
    assert cfg.chunk_samples == 512
    assert cfg.vad_threshold == 0.5
    assert cfg.stt_model == "small"
    assert cfg.stt_language == "zh"
    assert cfg.cleanup_timeout == 0.8
    assert cfg.tts_sample_rate == 24000
    assert cfg.continuous_idle_timeout == 10.0
