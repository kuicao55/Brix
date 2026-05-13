"""WakeWordProcessor 测试。"""

import sys
import pytest
from unittest.mock import MagicMock, patch

from capability.voice.processors.wake_word import WakeWordProcessor
from capability.voice.pipeline.frames import VoiceStateFrame


def _make_mock_model(confidence: float = 0.9, model_name: str = "hey_brix") -> MagicMock:
    """构造一个返回指定 confidence 的 mock Model。"""
    mock_model = MagicMock()
    mock_model.predict.return_value = {model_name: confidence}
    return mock_model


def _create_wakeword_mock_module(mock_model: MagicMock) -> dict:
    """构造 openwakeword 的 mock 模块结构，返回 sys.modules 补丁字典。"""
    mock_module = MagicMock()
    mock_module.Model.return_value = mock_model
    return {
        "openwakeword": MagicMock(),
        "openwakeword.model": mock_module,
    }


def _wake_up(proc: WakeWordProcessor, model_name: str = "hey_brix") -> None:
    """通过 mock Model 将处理器唤醒。"""
    mock_model = _make_mock_model(confidence=0.9, model_name=model_name)
    modules = _create_wakeword_mock_module(mock_model)
    with patch.dict(sys.modules, modules):
        proc.detect_sync(b"\x00\x01" * 256)


# ── 基础初始化 ──────────────────────────────────────────────────────────────

def test_wake_word_init():
    """WakeWordProcessor 可以初始化。"""
    proc = WakeWordProcessor(threshold=0.5)
    assert proc is not None
    assert not proc.is_awake


# ── process_audio_sync（公共 API）────────────────────────────────────────────

def test_process_audio_sync_passes_audio_when_awake():
    """唤醒后音频透传。"""
    proc = WakeWordProcessor(threshold=0.5, silence_limit_chunks=999)
    _wake_up(proc)
    assert proc.is_awake

    audio = b"\x00\x01" * 256
    result = proc.process_audio_sync(audio)
    assert result == audio


def test_process_audio_sync_drops_audio_when_sleeping():
    """未唤醒时音频被丢弃（返回 None）。"""
    proc = WakeWordProcessor(threshold=0.5)
    assert not proc.is_awake

    audio = b"\x00\x01" * 256
    result = proc.process_audio_sync(audio)
    assert result is None


# ── sleep() ─────────────────────────────────────────────────────────────────

def test_sleep_method_resets_state():
    """sleep() 方法将状态重置为休眠。"""
    proc = WakeWordProcessor(threshold=0.5, silence_limit_chunks=999)
    _wake_up(proc)
    assert proc.is_awake

    proc.sleep()
    assert not proc.is_awake


# ── reset() ─────────────────────────────────────────────────────────────────

def test_reset_clears_awake_and_silence_count():
    """reset() 清除 _awake 和 _silence_count。"""
    proc = WakeWordProcessor(threshold=0.5, silence_limit_chunks=999)
    _wake_up(proc)
    assert proc.is_awake
    assert proc._silence_count == 0

    # 模拟若干帧让 silence_count 增加
    proc.process_frame_sync(b"")  # 空音频 → silence_count + 1
    proc.process_frame_sync(b"")  # silence_count + 1
    assert proc._silence_count == 2

    proc.reset()
    assert not proc.is_awake
    assert proc._silence_count == 0


# ── detect_sync() — mock openwakeword ───────────────────────────────────────

def test_detect_sync_returns_true_when_confidence_exceeds_threshold():
    """confidence > threshold → 返回 True 并设置 is_awake。"""
    proc = WakeWordProcessor(threshold=0.5, model_name="hey_brix")
    mock_model = _make_mock_model(confidence=0.8)
    modules = _create_wakeword_mock_module(mock_model)

    with patch.dict(sys.modules, modules):
        result = proc.detect_sync(b"\x00\x01" * 256)

    assert result is True
    assert proc.is_awake is True
    mock_model.predict.assert_called_once()


def test_detect_sync_returns_false_when_confidence_below_threshold():
    """confidence < threshold → 返回 False，不改变 is_awake。"""
    proc = WakeWordProcessor(threshold=0.5, model_name="hey_brix")
    mock_model = _make_mock_model(confidence=0.2)
    modules = _create_wakeword_mock_module(mock_model)

    with patch.dict(sys.modules, modules):
        result = proc.detect_sync(b"\x00\x01" * 256)

    assert result is False
    assert proc.is_awake is False


def test_detect_sync_calls_ensure_model_lazy_loading():
    """detect_sync 调用 _ensure_model 实现懒加载 — Model 只构造一次。"""
    proc = WakeWordProcessor(threshold=0.5, model_name="hey_brix")
    mock_model = _make_mock_model(confidence=0.1)
    modules = _create_wakeword_mock_module(mock_model)
    mock_model_cls = modules["openwakeword.model"].Model

    with patch.dict(sys.modules, modules):
        proc.detect_sync(b"\x00\x01" * 256)

    # Model 构造函数应被调用一次（懒加载）
    mock_model_cls.assert_called_once_with(wakeword_models=["hey_brix"])

    # 第二次调用不应再次构造（_model 已缓存）
    mock_model_cls.reset_mock()
    with patch.dict(sys.modules, modules):
        proc.detect_sync(b"\x00\x01" * 256)
    mock_model_cls.assert_not_called()


# ── process_frame_sync() ────────────────────────────────────────────────────

def test_process_frame_sync_awake_returns_empty_on_normal_audio():
    """已唤醒 + 有音频 → 返回空列表（透传，不产生帧）。"""
    proc = WakeWordProcessor(threshold=0.5, silence_limit_chunks=999)
    _wake_up(proc)
    assert proc.is_awake

    # 正常音频 → 空列表
    result = proc.process_frame_sync(b"\x00\x01" * 256)
    assert result == []
    assert proc.is_awake  # 仍然唤醒


def test_process_frame_sync_awake_emits_sleep_after_silence_limit():
    """已唤醒 + 连续静默 silence_limit_chunks 次 → 输出 VoiceStateFrame(state="sleep")。"""
    limit = 5
    proc = WakeWordProcessor(threshold=0.5, silence_limit_chunks=limit)
    _wake_up(proc)
    assert proc.is_awake

    # 连续发送空音频（静默）达到限制
    for i in range(limit - 1):
        result = proc.process_frame_sync(b"")
        assert result == [], f"第 {i+1} 次静默不应产生帧"

    # 第 limit 次 → 触发 auto-sleep
    result = proc.process_frame_sync(b"")
    assert len(result) == 1
    assert isinstance(result[0], VoiceStateFrame)
    assert result[0].state == "sleep"
    assert not proc.is_awake


def test_process_frame_sync_sleep_emits_wake_detected_on_detection():
    """未唤醒 + 检测到唤醒词 → 输出 VoiceStateFrame(state="wake_detected")。"""
    proc = WakeWordProcessor(threshold=0.5, model_name="hey_brix")
    mock_model = _make_mock_model(confidence=0.9)
    modules = _create_wakeword_mock_module(mock_model)

    with patch.dict(sys.modules, modules):
        result = proc.process_frame_sync(b"\x00\x01" * 256)

    assert len(result) == 1
    assert isinstance(result[0], VoiceStateFrame)
    assert result[0].state == "wake_detected"
    assert proc.is_awake


def test_process_frame_sync_silence_count_resets_on_audio():
    """已唤醒 + 有音频时 silence_count 重置为 0（修复单调递增 bug）。"""
    limit = 5
    proc = WakeWordProcessor(threshold=0.5, silence_limit_chunks=limit)
    _wake_up(proc)
    assert proc.is_awake

    # 发送 3 次静默 → silence_count = 3
    for _ in range(3):
        proc.process_frame_sync(b"")
    assert proc._silence_count == 3

    # 发送有音频的帧 → silence_count 应重置为 0
    proc.process_frame_sync(b"\x00\x01" * 256)
    assert proc._silence_count == 0
    assert proc.is_awake  # 仍然唤醒

    # 再发 3 次静默 → 不应触发 auto-sleep（因为 count 从 0 开始）
    for _ in range(3):
        result = proc.process_frame_sync(b"")
        assert result == []
    assert proc.is_awake
