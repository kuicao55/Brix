"""CosyVoice TTS 客户端测试。"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from capability.voice.tts.cosyvoice_client import CosyVoiceClient, create_cosyvoice_client


def test_cosyvoice_client_init():
    """CosyVoiceClient 初始化参数正确。"""
    client = CosyVoiceClient(
        api_key="test-key",
        model="cosyvoice-v3-flash",
        voice="longxiaochun",
        sample_rate=24000,
    )
    assert client._api_key == "test-key"
    assert client._model == "cosyvoice-v3-flash"
    assert client._voice == "longxiaochun"
    assert client._sample_rate == 24000


def test_create_cosyvoice_client_from_config():
    """create_cosyvoice_client 从配置创建客户端。"""
    config = {
        "voice": {
            "tts_model": "cosyvoice-v3-flash",
            "tts_voice": "longxiaochun",
            "tts_api_key_env": "ALI_API_KEY",
            "tts_sample_rate": 24000,
        }
    }
    with patch.dict("os.environ", {"ALI_API_KEY": "test-key-123"}):
        client = create_cosyvoice_client(config)

    assert client is not None
    assert client._api_key == "test-key-123"
    assert client._model == "cosyvoice-v3-flash"


def test_create_cosyvoice_client_no_api_key():
    """无 API key 时返回 None。"""
    config = {
        "voice": {
            "tts_api_key_env": "NONEXISTENT_KEY",
        }
    }
    with patch.dict("os.environ", {}, clear=True):
        client = create_cosyvoice_client(config)

    assert client is None


def test_cosyvoice_normalize_text():
    """规整文本应去除异常符号并保留可读内容。"""
    client = CosyVoiceClient(api_key="test-key")
    text = "∴ 你好…\n`code` ⏺ ### 在干啥呀 😄"
    normalized = client._normalize_text(text)
    assert "你好" in normalized
    assert "在干啥呀" in normalized
    assert "∴" not in normalized
    assert "⏺" not in normalized
    assert "😄" not in normalized


def test_cosyvoice_prepare_text_segments():
    """长文本应被分段且每段不超过上限。"""
    client = CosyVoiceClient(api_key="test-key")
    long_text = "你好呀。" * 200
    segments = client._prepare_text_segments(long_text)
    assert len(segments) > 1
    assert all(len(seg) <= 180 for seg in segments)
    assert all(seg.strip() for seg in segments)


def test_cosyvoice_fallback_text():
    """fallback 文本应更简单且长度受限。"""
    client = CosyVoiceClient(api_key="test-key")
    text = "“你好”，（老大）《这是一个很长很长的句子》" * 20
    fallback = client._fallback_text(text)
    assert len(fallback) <= 80
    assert "“" not in fallback
    assert "（" not in fallback


def test_cosyvoice_is_speakable_segment_filters_short_english():
    """短英文或纯标点应被过滤。"""
    client = CosyVoiceClient(api_key="test-key")
    assert client._is_speakable_segment("你好呀") is True
    assert client._is_speakable_segment("........") is False
    assert client._is_speakable_segment("bug") is False
    assert client._is_speakable_segment("bug fixes today") is True


@pytest.mark.asyncio
async def test_synthesize_empty_text():
    """空文本不产生任何输出。"""
    client = CosyVoiceClient(api_key="test-key")
    chunks = []
    async for chunk in client.synthesize(""):
        chunks.append(chunk)
    assert chunks == []


@pytest.mark.asyncio
async def test_synthesize_whitespace_text():
    """纯空白文本不产生任何输出。"""
    client = CosyVoiceClient(api_key="test-key")
    chunks = []
    async for chunk in client.synthesize("   \n  "):
        chunks.append(chunk)
    assert chunks == []
