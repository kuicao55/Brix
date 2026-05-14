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
