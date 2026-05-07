"""Safe-boundary Markdown stream renderer using Rich Live."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown


class StreamRenderer:
    """Renders streamed Markdown at safe boundaries to avoid broken rendering.

    Safe boundaries:
      - After a fully closed code fence (``` ... ```)
      - After a blank line (paragraph break)
      - After any newline outside a code fence

    Content accumulates in ``pending`` until a safe boundary is found,
    then the ready portion moves to ``rendered`` and the Live display updates.
    """

    def __init__(self, console: Console) -> None:
        self.console = console
        self.pending = ""
        self.rendered = ""
        self.live = None

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
        """Re-render the accumulated content in the Live display."""
        if self.live and self.rendered:
            md = Markdown(self.rendered)
            self.live.update(md)
