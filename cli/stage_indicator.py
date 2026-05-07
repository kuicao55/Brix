"""Compact pipeline stage progress display."""

from __future__ import annotations

from rich.console import Console

from cli.spinner import Spinner

STAGE_ICON = "\u2739"


class StageIndicator:
    """Prints compact one-line summaries for each pipeline stage."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self._active_spinner: Spinner | None = None

    def stage_done(self, name: str, elapsed: float, detail: str = "") -> None:
        """Print a completed stage line with icon, name, time, and optional detail."""
        parts = ["  ", STAGE_ICON, " ", name, "  ", "{:.1f}s".format(elapsed)]
        if detail:
            parts.extend(["  ", detail])
        self.console.print("".join(parts), highlight=False)

    def stage_active(self, name: str) -> Spinner:
        """Start a Spinner for the current active stage and return it."""
        spinner = Spinner(self.console, label=name)
        spinner.start()
        self._active_spinner = spinner
        return spinner

    def finish(self) -> None:
        """Stop any active spinner."""
        if self._active_spinner is not None:
            self._active_spinner.finish()
            self._active_spinner = None
