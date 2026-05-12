"""Unified loading spinner — single animated line, updates in-place."""

from __future__ import annotations

from rich.console import Console

from cli.spinner import Spinner

STAGE_LABELS = {
    "Memory": "Loading memory...",
    "Intent": "Classifying intent...",
    "Complexity": "Evaluating complexity...",
    "Route": "Selecting model...",
    "Planning": "Planning...",
}


class StageIndicator:
    """Single animated spinner line that updates label as stages transition.

    Unlike the old multi-line approach, this shows ONE spinner line
    (like Claude Code) that stays in-place and updates its text.
    The line disappears when finish() is called (transient Live).
    """

    def __init__(self, console: Console, label: str = "Thinking...") -> None:
        self._spinner = Spinner(console, label=label)
        self._spinner.start()
        self._finished = False

    def update(self, stage: str, detail: str = "") -> None:
        """Update spinner label for the current pipeline stage."""
        if self._finished:
            return
        label = STAGE_LABELS.get(stage, "Working...")
        if detail:
            label = "{} ({})".format(label, detail)
        self._spinner.update_label(label)

    def finish(self) -> None:
        """Stop spinner silently — line disappears (transient Live)."""
        if self._finished:
            return
        self._finished = True
        self._spinner.stop()

    def stop_silent(self) -> None:
        """Stop spinner without printing anything. Used when StreamRenderer takes over."""
        if self._finished:
            return
        self._finished = True
        self._spinner.stop()
