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

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within max_tokens. Uses encoder when available."""
        if not text:
            return ""
        if self._encoder is not None:
            tokens = self._encoder.encode(text)
            if len(tokens) <= max_tokens:
                return text
            return self._encoder.decode(tokens[:max_tokens])
        # Fallback: approximate with chars
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars]

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

        # If system messages alone exceed the budget, truncate to fit
        if remaining <= 0:
            if not system_msgs:
                return []
            # Reserve tokens for the "[truncated]" marker on the last truncated message
            marker = "\n[truncated]"
            marker_tokens = self._count_tokens(marker)
            budget = max(marker_tokens + 1, limit)
            result: list[dict[str, Any]] = []
            used = 0
            for i, msg in enumerate(system_msgs):
                content = msg.get("content") or ""
                msg_tokens = self._count_tokens(content)
                if used + msg_tokens <= budget:
                    result.append(msg)
                    used += msg_tokens
                else:
                    # Truncate this message to fit remaining budget (reserve marker space)
                    remaining_budget = max(1, budget - used - marker_tokens)
                    truncated_content = self._truncate_to_tokens(content, remaining_budget)
                    if truncated_content:
                        result.append({**msg, "content": truncated_content + marker})
                    break
            # Guarantee at least one system message is always returned
            if not result and system_msgs:
                result.append({**system_msgs[0], "content": "[system prompt truncated to fit budget]"})
            return result

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
