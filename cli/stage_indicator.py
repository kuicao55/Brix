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

    def __init__(self, console: Console) -> None:
        self._spinner = Spinner(console, label="Thinking...")
        self._spinner.start()

    def update(self, stage: str) -> None:
        """Update spinner label for the current pipeline stage."""
        label = STAGE_LABELS.get(stage, "Working...")
        self._spinner.update_label(label)

    def finish(self) -> None:
        """Stop spinner silently — line disappears (transient Live)."""
        self._spinner.stop()
