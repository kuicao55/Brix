"""Memory strategy: when to save and how to build context windows."""

from __future__ import annotations

from typing import Any


class MemoryStrategy:
    """Decide what gets persisted and how much history to send to the LLM."""

    def __init__(self, max_tokens: int = 8000) -> None:
        self.max_tokens = max_tokens
        self._encoder = None
        try:
            import tiktoken

            self._encoder = tiktoken.encoding_for_model("gpt-4")
        except Exception:
            pass  # Graceful fallback to char-based counting

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text. Falls back to char/4 if tiktoken unavailable."""
        if not text:
            return 0
        if self._encoder is not None:
            return len(self._encoder.encode(text))
        return max(1, len(text) // 4)

    def should_save(self, message: dict[str, Any]) -> bool:
        """MVP: always save every message."""
        return True

    def get_context_window(
        self,
        history: list[dict[str, Any]],
        max_tokens: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return the most recent messages that fit within *max_tokens*.

        Walks backwards from the end of *history* and accumulates messages
        until the combined token count would exceed *max_tokens*.
        System messages are always preserved.
        """
        limit = max_tokens if max_tokens is not None else self.max_tokens

        # Separate system messages (always included)
        system_msgs = [m for m in history if m.get("role") == "system"]
        non_system = [m for m in history if m.get("role") != "system"]

        # Count system messages against budget
        system_tokens = sum(
            self._count_tokens(m.get("content") or "") for m in system_msgs
        )
        remaining = limit - system_tokens

        # If system messages alone exceed the budget, return only system messages
        if remaining <= 0:
            return system_msgs

        # Walk backwards through non-system messages
        total = 0
        window: list[dict[str, Any]] = []
        for msg in reversed(non_system):
            msg_tokens = self._count_tokens(msg.get("content") or "")
            if total + msg_tokens > remaining and window:
                break
            window.append(msg)
            total += msg_tokens
        window.reverse()

        # Prepend system messages
        return system_msgs + window
