"""AudioPlayer 测试。"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from capability.voice.transport.audio_player import AudioPlayer


def test_audio_player_init():
    """AudioPlayer 初始化参数正确。"""
    player = AudioPlayer(sample_rate=24000, channels=1, sample_width=2)
    assert player._sample_rate == 24000
    assert player._channels == 1
    assert player._sample_width == 2
    assert player.is_active is False


def test_audio_player_no_pyaudio():
    """无 PyAudio 时 start() 不崩溃。"""
    player = AudioPlayer()
    with patch("capability.voice.transport.audio_player.pyaudio", None):
        # 不应抛异常
        import asyncio
        asyncio.get_event_loop().run_until_complete(player.start())
        assert player.is_active is False


@pytest.mark.asyncio
async def test_audio_player_start_stop():
    """AudioPlayer 启动和停止生命周期。"""
    mock_pa = MagicMock()
    mock_stream = MagicMock()
    mock_pa.open.return_value = mock_stream

    player = AudioPlayer(sample_rate=24000)
    with patch("capability.voice.transport.audio_player.pyaudio") as mock_pyaudio:
        mock_pyaudio.PyAudio.return_value = mock_pa
        mock_pyaudio.paInt16 = 8

        await player.start()
        assert player.is_active is True
        mock_pa.open.assert_called_once()

        await player.stop()
        assert player.is_active is False
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_pa.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_audio_player_play_chunks():
    """AudioPlayer 播放 PCM chunks。"""
    mock_pa = MagicMock()
    mock_stream = MagicMock()
    mock_pa.open.return_value = mock_stream

    player = AudioPlayer(sample_rate=24000)
    with patch("capability.voice.transport.audio_player.pyaudio") as mock_pyaudio:
        mock_pyaudio.PyAudio.return_value = mock_pa
        mock_pyaudio.paInt16 = 8

        await player.start()

        # 模拟 chunks
        async def mock_chunks():
            yield b"audio_chunk_1"
            yield b"audio_chunk_2"

        await player.play_chunks(mock_chunks())

        await player.stop()


@pytest.mark.asyncio
async def test_audio_player_play_chunks_stops_on_inactive():
    """AudioPlayer 在非活跃状态时停止播放。"""
    player = AudioPlayer(sample_rate=24000)
    player._active = False  # 模拟非活跃

    async def mock_chunks():
        yield b"chunk"
        yield b"chunk2"

    # 不应崩溃
    await player.play_chunks(mock_chunks())
