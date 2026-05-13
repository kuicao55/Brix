"""WakeWordProcessor 测试。"""

import pytest
from unittest.mock import MagicMock, patch

from capability.voice.processors.wake_word import WakeWordProcessor


def test_wake_word_init():
    """WakeWordProcessor 可以初始化。"""
    proc = WakeWordProcessor(threshold=0.5)
    assert proc is not None
    assert not proc.is_awake


def test_wake_word_sleep_mode_passes_audio():
    """唤醒后音频透传。"""
    proc = WakeWordProcessor(threshold=0.5)
    proc._awake = True  # 手动设置为已唤醒

    audio = b"\x00\x01" * 256
    result = proc.process_audio_sync(audio)
    assert result == audio


def test_wake_word_sleep_mode_drops_audio():
    """未唤醒时音频被丢弃（返回 None）。"""
    proc = WakeWordProcessor(threshold=0.5)
    proc._awake = False

    audio = b"\x00\x01" * 256
    result = proc.process_audio_sync(audio)
    assert result is None


def test_wake_word_sleep_method():
    """sleep() 方法将状态重置为休眠。"""
    proc = WakeWordProcessor(threshold=0.5)
    proc._awake = True
    proc.sleep()
    assert not proc.is_awake
