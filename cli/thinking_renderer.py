"""Thinking content renderer — dimmed text with auto-collapse."""

from __future__ import annotations

import time

from rich.console import Console
from rich.live import Live
from rich.text import Text

# Braille frames for the thinking spinner.
BRAILLE_FRAMES = [
    "\u280b", "\u2819", "\u2839", "\u2838", "\u283c",
    "\u2834", "\u2826", "\u2827", "\u2807", "\u280f",
]

_COLLAPSE_THRESHOLD = 500  # 超过此字符数自动折叠
_VISIBLE_CHARS = 200       # 折叠后可见字符数


class ThinkingRenderer:
    """流式渲染 thinking/reasoning 内容。

    样式：灰色（dim）文字 + ∴ 前缀 + Braille spinner
    超过 _COLLAPSE_THRESHOLD 字符时自动折叠。
    """

    def __init__(self, console: Console) -> None:
        self.console = console
        self._live: Live | None = None
        self._content = ""
        self._start_time = 0.0
        self._last_delta_time = 0.0

    def start(self) -> None:
        """启动 Live 显示。"""
        self._start_time = time.monotonic()
        self._last_delta_time = self._start_time
        self._live = Live(
            self._build_display(),
            console=self.console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.start()

    def push_delta(self, text: str) -> None:
        """追加 thinking 文本并刷新显示。"""
        self._content += text
        self._last_delta_time = time.monotonic()
        if self._live:
            self._live.update(self._build_display())

    def flush(self) -> None:
        """停止 Live 并打印最终内容。"""
        if self._live:
            self._live.stop()
            self._live = None

        if not self._content:
            return

        elapsed = time.monotonic() - self._start_time
        # 打印最终的 thinking 内容（折叠或完整）
        output = Text()
        output.append("∴ ", style="dim cyan")
        if len(self._content) > _COLLAPSE_THRESHOLD:
            visible = self._content[:_VISIBLE_CHARS]
            remaining = len(self._content) - _VISIBLE_CHARS
            output.append(visible, style="dim")
            output.append(f" ... [{remaining} more chars]", style="dim cyan")
        else:
            output.append(self._content, style="dim")
        output.append(f"  ({elapsed:.1f}s)", style="dim cyan")
        self.console.print(output)

    def _build_display(self) -> Text:
        """构建实时显示内容。"""
        elapsed = time.monotonic() - self._start_time
        frame_idx = int(time.monotonic() * 10) % len(BRAILLE_FRAMES)
        frame = BRAILLE_FRAMES[frame_idx]

        display = Text()
        display.append(f"{frame} ", style="spinner.active")
        display.append("Thinking ", style="dim")

        # 显示已累积的字符数
        if self._content:
            display.append(f"({len(self._content)} chars) ", style="dim cyan")

        # 显示最近的文本片段（最多 80 字符）
        if self._content:
            tail = self._content[-80:].replace("\n", " ")
            display.append(tail, style="dim")

        display.append(f"  {elapsed:.1f}s", style="dim cyan")
        return display
