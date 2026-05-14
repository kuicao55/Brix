"""VoiceDisplay — 语音转录实时可视化 + 每步耗时。"""

from __future__ import annotations

import time

from rich.console import Console
from rich.live import Live
from rich.text import Text

BRAILLE_FRAMES = [
    "\u280b", "\u2819", "\u2839", "\u2838", "\u283c",
    "\u2834", "\u2826", "\u2827", "\u2807", "\u280f",
]

_MARKER = "\U0001f3a4 "  # 🎤


class VoiceDisplay:
    """语音转录实时显示 + 每步耗时。

    状态流转：
    - listening:  🎤 listening... ⠋
    - processing: 🎤 STT: 2300ms ⠙
    - cleanup:    🎤 STT: 2300ms → Cleanup: 800ms ⠙
    - final:      🎤 STT: 2300ms → Cleanup: 800ms = 你好世界
    """

    def __init__(self, console: Console) -> None:
        self._console = console
        self._live: Live | None = None
        self._text = ""
        self._state = "idle"
        self._start_time = 0.0
        self._timings: dict[str, int] = {}  # step -> ms

    def start_listening(self) -> None:
        """用户开始说话。"""
        if self._state in ("listening", "processing", "cleanup"):
            return
        self._state = "listening"
        self._text = ""
        self._timings = {}
        self._start_time = time.monotonic()
        self._ensure_live()

    def update_timing(self, step: str, ms: int) -> None:
        """更新某步骤的耗时。"""
        self._timings[step] = ms
        if step == "stt":
            self._state = "processing"
        elif step == "cleanup":
            self._state = "cleanup"
        if self._live:
            self._live.update(self._build_display())

    def update_interim(self, text: str) -> None:
        """更新 interim 转录文本。"""
        self._text = text
        if self._live:
            self._live.update(self._build_display())

    def finish(self, final_text: str) -> None:
        """显示最终结果（持久）。"""
        self._state = "final"
        self._text = final_text
        if self._live:
            self._live.stop()
            self._live = None

        # 打印持久化结果 + timing
        display = Text()
        display.append(_MARKER, style="green")
        display.append(self._text, style="bold")
        display.append("  ")
        display.append(self._format_timing(), style="dim")
        self._console.print(display)

    def stop(self) -> None:
        """停止显示。"""
        if self._live:
            self._live.stop()
            self._live = None
        self._state = "idle"
        self._text = ""
        self._timings = {}

    def _ensure_live(self) -> None:
        if self._live is not None:
            return
        self._live = Live(
            self._build_display(),
            console=self._console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.start()

    def _format_timing(self) -> str:
        """格式化 timing: STT: 2300ms → Cleanup: 800ms (total: 3100ms)"""
        if not self._timings:
            return ""
        parts = []
        total = 0
        for step in ("stt", "cleanup"):
            if step in self._timings:
                ms = self._timings[step]
                total += ms
                label = step.upper()
                parts.append(f"{label}: {ms}ms")
        if parts:
            return " → ".join(parts) + f" (total: {total}ms)"
        return ""

    def _build_display(self) -> Text:
        frame_idx = int(time.monotonic() * 10) % len(BRAILLE_FRAMES)
        spinner = BRAILLE_FRAMES[frame_idx]
        elapsed = time.monotonic() - self._start_time

        display = Text()
        display.append(_MARKER, style="cyan")

        if self._state == "listening":
            display.append("listening...", style="dim")
            display.append(f" {spinner}", style="cyan")
            display.append(f"  {elapsed:.1f}s", style="dim")

        elif self._state in ("processing", "cleanup"):
            # 显示已完成的步骤耗时
            timing_str = self._format_timing()
            if timing_str:
                display.append(timing_str, style="yellow")
            display.append(f" {spinner}", style="cyan")
            display.append(f"  {elapsed:.1f}s", style="dim")

        elif self._state == "final":
            display.append(self._text, style="bold")
            display.append("  ")
            display.append(self._format_timing(), style="dim")

        else:
            display.append(self._text, style="dim")

        return display
