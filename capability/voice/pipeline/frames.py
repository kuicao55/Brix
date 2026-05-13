"""自定义 Frame 类型 — Voice 模块专用。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VoiceStateFrame:
    """语音状态变化帧 — 通知 pipeline 外部状态。"""
    state: str  # "wake_detected" | "speech_start" | "speech_end" | "processing" | "speaking" | "error"
    error: str = ""
    processor: str = ""


@dataclass
class CleanedTextFrame:
    """LLM Cleanup 后的干净文本帧。"""
    text: str
    raw_text: str = ""  # 原始识别文本，用于调试
