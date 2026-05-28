"""自定义 Frame 类型测试。"""

from capability.voice.pipeline.frames import (
    VoiceStateFrame,
    CleanedTextFrame,
)


def test_voice_state_frame():
    """VoiceStateFrame 可以携带状态。"""
    frame = VoiceStateFrame(state="wake_detected")
    assert frame.state == "wake_detected"


def test_voice_state_frame_with_error():
    """VoiceStateFrame 可以携带错误信息。"""
    frame = VoiceStateFrame(state="processor_error", error="STT failed", processor="STTProcessor")
    assert frame.state == "processor_error"
    assert frame.error == "STT failed"
    assert frame.processor == "STTProcessor"


def test_cleaned_text_frame():
    """CleanedTextFrame 可以携带润色文本和原始文本。"""
    frame = CleanedTextFrame(text="你好世界", raw_text="嗯 你好世界")
    assert frame.text == "你好世界"
    assert frame.raw_text == "嗯 你好世界"
