"""Pipeline builder 测试。"""

import asyncio
import threading

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from capability.voice.pipeline.builder import (
    INTERIM_MAX_AUDIO_BYTES,
    INTERIM_MIN_AUDIO_BYTES,
    INTERIM_PERIODIC_CHUNKS,
    build_voice_pipeline,
)
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
    """Pipeline 传递音频数据到 STT 并产生文本。

    模拟真实流程：speech_start → 若干音频 chunk → speech_end → 转录。
    """
    mock_transport = MagicMock()
    mock_transport.audio_queue = asyncio.Queue()

    # VAD 返回序列：先 speech_start，然后两次无帧（语音中），最后 speech_end
    mock_vad = MagicMock()
    mock_vad.process_frame_sync.side_effect = [
        [VoiceStateFrame(state="speech_start")],  # 第 1 个 chunk：检测到语音开始
        [],  # 第 2 个 chunk：语音进行中
        [],  # 第 3 个 chunk：语音进行中
        [VoiceStateFrame(state="speech_end")],  # 第 4 个 chunk：语音结束
    ]

    # STT：音频帧缓冲返回空，speech_end 触发转录返回文本
    mock_stt = MagicMock()

    def _stt_side_effect(frame):
        if isinstance(frame, VoiceStateFrame) and frame.state == "speech_end":
            return [CleanedTextFrame(text="你好", raw_text="你好")]
        return []

    mock_stt.process_frame_sync.side_effect = _stt_side_effect

    mock_cleanup = AsyncMock()
    mock_cleanup.process.return_value = CleanedTextFrame(text="你好", raw_text="你好")

    final_texts = []
    pipeline = build_voice_pipeline(
        audio_source=mock_transport,
        vad=mock_vad,
        stt=mock_stt,
        cleanup=mock_cleanup,
        on_final_text=lambda t: final_texts.append(t),
        post_speech_wait_ms=0,
    )

    # 放入 4 个音频 chunk
    for _ in range(4):
        await mock_transport.audio_queue.put(b"\x00\x01" * 256)

    await pipeline.start()
    await asyncio.sleep(0.5)  # Let process loop run
    await pipeline.stop()

    assert "你好" in final_texts


@pytest.mark.asyncio
async def test_pipeline_drops_stale_interim_after_speech_end():
    """speech_end 后产生的过期 interim 不应触发 UI 回调。"""
    mock_transport = MagicMock()
    mock_transport.audio_queue = asyncio.Queue()
    mock_vad = MagicMock()
    mock_stt = MagicMock()
    mock_cleanup = AsyncMock()
    interim_cb = MagicMock()

    pipeline = build_voice_pipeline(
        audio_source=mock_transport,
        vad=mock_vad,
        stt=mock_stt,
        cleanup=mock_cleanup,
        on_interim_text=interim_cb,
    )
    pipeline._speech_active = True
    pipeline._utterance_id = 1

    def _slow_interim(_audio: bytes, _cancel: threading.Event) -> str:
        import time

        time.sleep(0.05)
        return "旧 interim"

    mock_stt.transcribe_interim.side_effect = _slow_interim
    cancel = threading.Event()

    task = asyncio.create_task(
        pipeline._do_interim_transcription(b"\x00\x01" * 12000, cancel, utterance_id=1)
    )
    await asyncio.sleep(0.01)
    pipeline._speech_active = False
    pipeline._utterance_id = 2
    await task

    interim_cb.assert_not_called()


def test_pipeline_skips_new_interim_when_previous_running():
    """已有 in-flight interim 时，不再重复入队。"""
    mock_transport = MagicMock()
    mock_vad = MagicMock()
    mock_stt = MagicMock()
    mock_cleanup = AsyncMock()

    pipeline = build_voice_pipeline(
        audio_source=mock_transport,
        vad=mock_vad,
        stt=mock_stt,
        cleanup=mock_cleanup,
        on_interim_text=lambda _text: None,
    )
    pipeline._speech_active = True
    pipeline._chunks_since_interim = INTERIM_PERIODIC_CHUNKS

    inflight_task = MagicMock()
    inflight_task.done.return_value = False
    pipeline._interim_task = inflight_task

    pipeline._update_speech_state(vad_frames=[])
    mock_stt.get_buffer_audio.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_interim_uses_tail_window():
    """interim 只使用最近窗口，避免整段音频拖慢。"""
    mock_transport = MagicMock()
    mock_vad = MagicMock()
    mock_stt = MagicMock()
    mock_cleanup = AsyncMock()

    pipeline = build_voice_pipeline(
        audio_source=mock_transport,
        vad=mock_vad,
        stt=mock_stt,
        cleanup=mock_cleanup,
        on_interim_text=lambda _text: None,
    )
    pipeline._speech_active = True
    pipeline._chunks_since_interim = INTERIM_PERIODIC_CHUNKS
    pipeline._silence_chunks = 0

    long_audio = b"\x01\x02" * (INTERIM_MAX_AUDIO_BYTES + 8000)
    assert len(long_audio) > INTERIM_MIN_AUDIO_BYTES
    mock_stt.get_buffer_audio.return_value = long_audio

    with patch.object(pipeline, "_do_interim_transcription", new_callable=AsyncMock) as do_interim:
        pipeline._update_speech_state(vad_frames=[])

    do_interim.assert_called_once()
    called_audio = do_interim.call_args.args[0]
    assert len(called_audio) == INTERIM_MAX_AUDIO_BYTES
    assert called_audio == long_audio[-INTERIM_MAX_AUDIO_BYTES:]
