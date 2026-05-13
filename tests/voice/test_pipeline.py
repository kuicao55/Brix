"""Pipeline builder 测试。"""

import asyncio

import pytest
from unittest.mock import MagicMock, AsyncMock

from capability.voice.pipeline.builder import build_voice_pipeline
from capability.voice.pipeline.frames import VoiceStateFrame, CleanedTextFrame


def test_build_voice_pipeline():
    mock_transport = MagicMock()
    mock_vad = MagicMock()
    mock_stt = MagicMock()
    mock_cleanup = MagicMock()
    pipeline = build_voice_pipeline(
        audio_source=mock_transport,
        vad=mock_vad,
        stt=mock_stt,
        cleanup=mock_cleanup,
    )
    assert pipeline is not None
    assert len(pipeline.processors) == 4


@pytest.mark.asyncio
async def test_pipeline_feeds_audio_to_stt():
    """Pipeline 传递音频数据到 STT 并产生文本。"""
    mock_transport = MagicMock()
    mock_transport.audio_queue = asyncio.Queue()

    # VAD returns speech_end after one chunk
    mock_vad = MagicMock()
    mock_vad.process_frame_sync.return_value = [VoiceStateFrame(state="speech_end")]

    # STT returns cleaned text on speech_end
    mock_stt = MagicMock()
    mock_stt.process_frame_sync.side_effect = [
        [],  # audio frame -> buffered, no output
        [CleanedTextFrame(text="你好", raw_text="你好")],  # speech_end -> transcribe
    ]

    mock_cleanup = AsyncMock()
    mock_cleanup.process.return_value = CleanedTextFrame(text="你好", raw_text="你好")

    final_texts = []
    pipeline = build_voice_pipeline(
        audio_source=mock_transport,
        vad=mock_vad,
        stt=mock_stt,
        cleanup=mock_cleanup,
        on_final_text=lambda t: final_texts.append(t),
    )

    # Put one audio chunk
    await mock_transport.audio_queue.put(b"\x00\x01" * 256)

    await pipeline.start()
    await asyncio.sleep(0.3)  # Let process loop run
    await pipeline.stop()

    assert "你好" in final_texts
