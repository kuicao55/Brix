"""Safe-boundary Markdown stream renderer using Rich Live."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.segment import Segment
from rich.text import Text

# Visual width of the ``  ⏺ `` marker (2 spaces + circle + 1 space).
_MARKER_WIDTH = 4


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
        self._md = Markdown(source)
        self._marker_text = marker_text
        self._marker_style = marker_style
        self._console = console

    def __rich_console__(self, console, options):
        style = self._console.get_style(self._marker_style)
        # Marker on the first line, inline with content
        yield Segment(self._marker_text, style)
        # Render Markdown, inserting indent after every newline
        for seg in self._md.__rich_console__(console, options):
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

    def start(self) -> None:
        """Start the Rich Live display."""
        self.live = Live(
            console=self.console,
            refresh_per_second=15,
            transient=False,
        )
        self.live.start()

    def push_delta(self, delta: str) -> None:
        """Append a text delta and render if a safe boundary is reached."""
        self.pending += delta
        boundary = self._find_safe_boundary(self.pending)
        if boundary is not None:
            ready = self.pending[:boundary]
            self.pending = self.pending[boundary:]
            self.rendered += ready
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

    def _update_display(self) -> None:
        """Re-render the accumulated content in the Live display.

        If a marker was provided, it is rendered inline on the first line
        of the content via ``_MarkerMarkdown``.  Every subsequent line is
        indented by ``_MARKER_WIDTH`` columns so the body aligns under the
        marker.
        """
        if self.live and self.rendered:
            if self._marker is not None:
                style = self._marker.style if isinstance(self._marker.style, str) else "green"
                renderable = _MarkerMarkdown(
                    self.rendered,
                    self._marker.plain,
                    style,
                    self.console,
                )
            else:
                renderable = Markdown(self.rendered)
            self.live.update(renderable)
