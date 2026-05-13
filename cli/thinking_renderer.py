"""Thinking content renderer — dimmed text with marker-style layout."""

from __future__ import annotations

import time

from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.padding import Padding
from rich.segment import Segment
from rich.text import Text

# Braille frames for the thinking spinner.
BRAILLE_FRAMES = [
    "\u280b", "\u2819", "\u2839", "\u2838", "\u283c",
    "\u2834", "\u2826", "\u2827", "\u2807", "\u280f",
]

_COLLAPSE_THRESHOLD = 500  # 超过此字符数折叠显示摘要
_MARKER = "\u2234 "  # ∴
_MARKER_WIDTH = len(_MARKER)


class _MarkerText:
    """Renderable: ∴ marker on first line, content indented to align.

    Same approach as stream_renderer._MarkerMarkdown but for plain Text.
    Uses Padding to indent all lines, then replaces the first padding
    with the styled marker so content starts right after ``∴ ``.
    """

    def __init__(self, content: str, marker_text: str, marker_style: str, content_style: str, console: Console) -> None:
        self._text = Text(content, style=content_style)
        self._marker_text = marker_text
        self._marker_style = marker_style
        self._console = console

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        style = self._console.get_style(self._marker_style)
        padded = Padding(self._text, (0, 0, 0, _MARKER_WIDTH))
        replaced = False
        for seg in padded.__rich_console__(console, options):
            if (
                not replaced
                and seg.control is None
                and seg.text == " " * _MARKER_WIDTH
            ):
                yield Segment(self._marker_text, style)
                replaced = True
            else:
                yield seg


class ThinkingRenderer:
    """流式渲染 thinking/reasoning 内容。

    布局：∴ 标记在左侧，内容在右侧（与 ⏺ 标记一致）。
    超过 _COLLAPSE_THRESHOLD 字符时折叠为摘要行。
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
            self._build_streaming_display(),
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
            self._live.update(self._build_streaming_display())

    def flush(self) -> None:
        """停止 Live 并打印最终内容。"""
        if self._live:
            self._live.stop()
            self._live = None

        if not self._content:
            return

        elapsed = time.monotonic() - self._start_time

        if len(self._content) > _COLLAPSE_THRESHOLD:
            # 折叠：只显示摘要行
            summary = Text()
            summary.append(_MARKER, style="dim cyan")
            summary.append(f"Thought for {elapsed:.1f}s ({len(self._content)} chars)", style="dim")
            self.console.print(summary)
        else:
            # 完整显示：∴ 标记 + 内容右对齐
            renderable = _MarkerText(
                self._content,
                marker_text=_MARKER,
                marker_style="dim cyan",
                content_style="dim",
                console=self.console,
            )
            self.console.print(renderable)

    def _build_streaming_display(self) -> _MarkerText:
        """构建流式实时显示：∴ + 最近内容尾部。"""
        # 显示最近的内容尾部（最多 200 字符），保持与 flush 一致的布局
        tail = self._content[-200:].replace("\n", " ") if self._content else ""
        elapsed = time.monotonic() - self._start_time
        frame_idx = int(time.monotonic() * 10) % len(BRAILLE_FRAMES)
        frame = BRAILLE_FRAMES[frame_idx]

        display_text = f"{frame} {tail}  {elapsed:.1f}s" if tail else f"{frame} Thinking...  {elapsed:.1f}s"
        return _MarkerText(
            display_text,
            marker_text=_MARKER,
            marker_style="dim cyan",
            content_style="dim",
            console=self.console,
        )
