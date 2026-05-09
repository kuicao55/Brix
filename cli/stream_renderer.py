"""Safe-boundary Markdown stream renderer using Rich Live."""

from __future__ import annotations

import time

from rich.console import Console
from rich.console import Group
from rich.live import Live
from rich.markdown import Markdown
from rich.segment import Segment
from rich.text import Text

# Braille frames reused from spinner.py for the embedded activity indicator.
BRAILLE_FRAMES = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]

# Visual width of the ``  ⏺ `` marker (2 spaces + circle + 1 space).
_MARKER_WIDTH = 4


class _CompactMarkdown:
    """Markdown renderable that filters out blank-line segments for tighter
    paragraph spacing.

    Rich's Markdown renderer adds a blank-line ``Segment('\n')`` between block
    elements (paragraphs, headings, code blocks).  This wrapper removes those
    consecutive newlines so paragraphs appear single-spaced.
    """

    def __init__(self, source: str, console: Console) -> None:
        self._md = Markdown(source)
        self._console = console

    def __rich_console__(self, console, options):
        prev_was_newline = False
        for seg in self._md.__rich_console__(console, options):
            is_newline = seg.text == "\n" and seg.control is None
            if is_newline and prev_was_newline:
                continue  # skip blank-line segment
            prev_was_newline = is_newline
            yield seg


class _MarkerMarkdown:
    """Renderable that places a styled marker inline with the first line
    of a Markdown block and indents every subsequent line by
    ``_MARKER_WIDTH`` columns so the response body aligns under the marker.
    """

    def __init__(
        self,
        source: str,
        marker_text: str,
        marker_style: str,
        console: Console,
    ) -> None:
        self._md = _CompactMarkdown(source, console)
        self._marker_text = marker_text
        self._marker_style = marker_style
        self._console = console

    def __rich_console__(self, console, options):
        style = self._console.get_style(self._marker_style)
        # Marker on the first line, inline with content
        yield Segment(self._marker_text, style)
        # Reduce available width so Rich wraps content within the indented zone
        inner_width = max(20, options.max_width - _MARKER_WIDTH)
        inner_options = options.update_width(inner_width)
        # Render Markdown with reduced width, inserting indent after every newline
        for seg in self._md.__rich_console__(console, inner_options):
            yield seg
            if seg.text == "\n":
                yield Segment(" " * _MARKER_WIDTH)


class StreamRenderer:
    """Renders streamed Markdown at safe boundaries to avoid broken rendering.

    Safe boundaries:
      - After a fully closed code fence (``` ... ```)
      - After a blank line (paragraph break)
      - After any newline outside a code fence

    Content accumulates in ``pending`` until a safe boundary is found,
    then the ready portion moves to ``rendered`` and the Live display updates.
    """

    def __init__(self, console: Console, marker: Text | None = None) -> None:
        self.console = console
        self.pending = ""
        self.rendered = ""
        self.live = None
        self._marker = marker
        self._last_delta_time = 0.0
        self._indicator_label = "Waiting for tool call..."

    def start(self) -> None:
        """Start the Rich Live display."""
        self.live = Live(
            console=self.console,
            refresh_per_second=15,
            transient=False,
        )
        self.live.start()
        self._last_delta_time = time.monotonic()

    def push_delta(self, delta: str) -> None:
        """Append a text delta and render if a safe boundary is reached."""
        self._last_delta_time = time.monotonic()
        self.pending += delta
        boundary = self._find_safe_boundary(self.pending)
        if boundary is not None:
            ready = self.pending[:boundary]
            self.pending = self.pending[boundary:]
            self.rendered += ready
        # Always update display so activity indicator can appear during idle.
        self._update_display()

    def flush(self) -> None:
        """Render all remaining buffered content and stop the Live display."""
        if self.pending:
            self.rendered += self.pending
            self.pending = ""
            self._update_display()
        if self.live:
            self.live.stop()
            self.live = None

    def _find_safe_boundary(self, text: str):
        """Return the character position of the last safe rendering boundary.

        Returns None if no safe boundary exists yet.

        Safe boundaries:
          - After a fully closed code fence (``` ... ```)
          - After a blank line (paragraph break)
          - After any newline outside a code fence
        """
        lines = text.split("\n")
        in_fence = False
        last_safe = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                if not in_fence:
                    # Just closed a fence — safe boundary after this line
                    pos = sum(len(l) + 1 for l in lines[:i + 1])
                    last_safe = pos
            elif not in_fence and i > 0:
                # Any line break outside a fence is a safe boundary
                pos = sum(len(l) + 1 for l in lines[:i])
                last_safe = pos
        return last_safe if last_safe > 0 else None

    def _build_display(self):
        """Build display content: rendered Markdown + optional activity indicator.

        Returns a Rich renderable (Group when multiple parts, Text when empty).
        The activity indicator appears when idle > 0.8s with pending content,
        filling the visual gap between text stream end and tool call generation.
        """
        parts = []
        if self.rendered:
            if self._marker is not None:
                style = self._marker.style if isinstance(self._marker.style, str) else "green"
                parts.append(_MarkerMarkdown(
                    self.rendered,
                    self._marker.plain,
                    style,
                    self.console,
                ))
            else:
                parts.append(_CompactMarkdown(self.rendered, self.console))

        # Show activity indicator when idle > 0.8s with pending content
        if self.pending and time.monotonic() - self._last_delta_time > 0.8:
            frame_idx = int(time.monotonic() * 10) % len(BRAILLE_FRAMES)
            frame = BRAILLE_FRAMES[frame_idx]
            indicator = Text()
            indicator.append("\n  {} ".format(frame), style="spinner.active")
            indicator.append(self._indicator_label, style="dim")
            parts.append(indicator)

        return Group(*parts) if parts else Text("")

    def _update_display(self) -> None:
        """Re-render the accumulated content in the Live display.

        Delegates to ``_build_display()`` which assembles rendered Markdown
        and an optional activity indicator into a single renderable.
        """
        if self.live:
            self.live.update(self._build_display())
