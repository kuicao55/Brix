"""LocalAudioTransport 测试。"""

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from capability.voice.transport.local_audio import LocalAudioTransport
from capability.voice.config import VoiceConfig


def test_local_audio_transport_init():
    """LocalAudioTransport 可以用 VoiceConfig 初始化。"""
    cfg = VoiceConfig()
    transport = LocalAudioTransport(cfg)
    assert transport is not None
    assert not transport.is_active


@pytest.mark.asyncio
async def test_local_audio_transport_start_stop():
    """LocalAudioTransport 可以启动和停止。"""
    cfg = VoiceConfig()
    transport = LocalAudioTransport(cfg)

    with patch("capability.voice.transport.local_audio.pyaudio") as mock_pa:
        mock_instance = MagicMock()
        mock_pa.PyAudio.return_value = mock_instance
        mock_stream = MagicMock()
        mock_instance.open.return_value = mock_stream

        await transport.start()
        assert transport.is_active

        await transport.stop()
        assert not transport.is_active
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_instance.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_local_audio_transport_audio_queue():
    """麦克风回调将音频数据放入 asyncio Queue。"""
    cfg = VoiceConfig()
    transport = LocalAudioTransport(cfg)

    with patch("capability.voice.transport.local_audio.pyaudio") as mock_pa:
        mock_instance = MagicMock()
        mock_pa.PyAudio.return_value = mock_instance
        mock_stream = MagicMock()
        mock_instance.open.return_value = mock_stream

        await transport.start()

        test_data = b"\x00\x01" * 256
        transport._audio_callback(test_data, 256, None, None)

        data = await asyncio.wait_for(transport.audio_queue.get(), timeout=1.0)
        assert data == test_data

        await transport.stop()
