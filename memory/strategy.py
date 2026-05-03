"""Memory strategy: when to save and how to build context windows."""

from __future__ import annotations

from typing import Any


class MemoryStrategy:
    """Decide what gets persisted and how much history to send to the LLM."""

    def should_save(self, message: dict[str, Any]) -> bool:
        """MVP: always save every message."""
        return True

    def get_context_window(
        self,
        history: list[dict[str, Any]],
        max_chars: int = 4000,
    ) -> list[dict[str, Any]]:
        """Return the most recent messages that fit within *max_chars*.

        Walks backwards from the end of *history* and accumulates messages
        until the combined character count would exceed *max_chars*.
        """
        total = 0
        window: list[dict[str, Any]] = []
        for msg in reversed(history):
            msg_chars = len(msg.get("content", ""))
            if total + msg_chars > max_chars and window:
                break
            window.append(msg)
            total += msg_chars
        window.reverse()
        return window
