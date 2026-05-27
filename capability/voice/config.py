"""语音模块配置。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VoiceConfig:
    """语音模块配置。"""

    # 独立控制 STT / TTS
    input_enabled: bool = True   # 语音输入（麦克风 + VAD + STT）
    output_enabled: bool = True  # 语音输出（TTS 合成 + 播放）

    # 音频采集
    sample_rate: int = 16000
    channels: int = 1
    chunk_samples: int = 512  # Silero VAD 要求 512/1024/1536

    # VAD
    vad_threshold: float = 0.5
    min_speech_ms: int = 250
    min_silence_ms: int = 800  # 中文自然停顿较长，避免说话中间被截断
    post_speech_wait_ms: int = 1500  # speech_end 后等待续说的时间窗口

    # STT
    stt_provider: str = "local"  # local / online
    stt_model: str = "small"
    stt_interim_model: str = "tiny"
    stt_language: str = "zh"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    # 在线 STT (Qwen-ASR Realtime)
    stt_online_model: str = "qwen3-asr-flash-realtime"
    stt_online_language: str = "zh"
    stt_online_api_key_env: str = "ALI_API_KEY"

    # LLM Cleanup
    cleanup_enabled: bool = False  # 暂时禁用 LLM cleanup
    cleanup_model: str = ""  # 空 = 使用 intent_model
    cleanup_timeout: float = 0.8
    cleanup_min_length: int = 10  # 短句跳过 cleanup（长度 <= 此值跳过）

    # TTS (P1)
    tts_model: str = "cosyvoice-v3-flash"
    tts_voice: str = "longxiaochun"
    tts_api_key_env: str = "ALI_API_KEY"
    tts_sample_rate: int = 24000
    tts_prefetch_ms: int = 80
    tts_cooldown_ms: int = 800  # TTS 播放后冷却时间，防止回声循环

    # 唤醒词 (P2)
    wake_word_model: str = "hey_brix"
    wake_threshold: float = 0.5
    wake_idle_timeout: float = 15.0

    # 连续对话 (P4)
    continuous_idle_timeout: float = 10.0

    @classmethod
    def from_dict(cls, data: dict) -> VoiceConfig:
        """从 Brix 配置 dict 构造。只取 voice 子项。"""
        voice_data = data.get("voice", {})
        cfg = cls()
        for key, value in voice_data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg
