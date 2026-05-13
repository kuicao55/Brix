"""Pipeline builder 测试。"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from capability.voice.pipeline.builder import build_voice_pipeline


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
