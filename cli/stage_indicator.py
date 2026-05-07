"""Compact pipeline stage progress display."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape as markup_escape

from cli.spinner import Spinner

STAGE_ICON = "\u22b9"


class StageIndicator:
    """Prints compact one-line summaries for each pipeline stage."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self._active_spinner: Spinner | None = None

    def stage_done(self, name: str, elapsed: float, detail: str = "") -> None:
        """Print a completed stage line with icon, name, time, and optional detail."""
        parts = ["  ", STAGE_ICON, " ", markup_escape(name), "  ", "{:.1f}s".format(elapsed)]
        if detail:
            parts.extend(["  ", markup_escape(detail)])
        self.console.print("".join(parts), highlight=False)

    def stage_active(self, name: str) -> Spinner:
        """Start a Spinner for the current active stage and return it."""
        if self._active_spinner is not None:
            self._active_spinner.finish()
            self._active_spinner = None
        spinner = Spinner(self.console, label=name)
        spinner.start()
        self._active_spinner = spinner
        return spinner

    def finish(self) -> None:
        """Stop any active spinner."""
        if self._active_spinner is not None:
            self._active_spinner.finish()
            self._active_spinner = None
