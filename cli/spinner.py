"""Braille animation spinner with Rich Live display."""

from __future__ import annotations

import threading
import time

from rich.console import Console
from rich.live import Live
from rich.text import Text

BRAILLE_FRAMES = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]


class Spinner:
    """Braille animation spinner with elapsed-time display."""

    def __init__(self, console: Console, label: str = "Thinking...") -> None:
        self.console = console
        self.label = label
        self.frame_idx = 0
        self.start_time = 0.0
        self.running = False
        self.live = None
        self._thread = None

    def _render_frame(self) -> Text:
        elapsed = time.time() - self.start_time
        frame = BRAILLE_FRAMES[self.frame_idx % len(BRAILLE_FRAMES)]
        text = Text()
        text.append("  {} ".format(frame), style="spinner.active")
        text.append(self.label, style="dim")
        text.append("  {:.1f}s".format(elapsed), style="dim cyan")
        return text

    def start(self) -> None:
        """Start the spinner animation in a background thread."""
        self.running = True
        self.start_time = time.time()
        self.live = Live(
            self._render_frame(),
            console=self.console,
            refresh_per_second=10,
            transient=True,
        )
        self.live.start()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def _animate(self) -> None:
        while self.running:
            self.frame_idx += 1
            if self.live:
                self.live.update(self._render_frame())
            time.sleep(0.1)

    def update_label(self, label: str) -> None:
        """Change the spinner label while running."""
        self.label = label

    def finish(self, label: str = "Done") -> None:
        """Stop spinner and print a success message."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        if self.live:
            self.live.stop()
        elapsed = time.time() - self.start_time
        self.console.print("  [green]\u2713[/] {}  [dim]{:.1f}s[/]".format(label, elapsed))

    def fail(self, label: str = "Failed") -> None:
        """Stop spinner and print a failure message."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        if self.live:
            self.live.stop()
        elapsed = time.time() - self.start_time
        self.console.print("  [red]\u2717[/] {}  [dim]{:.1f}s[/]".format(label, elapsed))
