"""Intent classification using LLM."""

from __future__ import annotations

import re
from typing import Any

INTENT_SYSTEM_PROMPT = (
    "You are an intent classifier. "
    "Given the user message, classify it as one of: chat, task, tool_use. "
    "Respond with ONLY one of those three words."
)

_TOOL_KEYWORDS = ["weather", "calculate", "read file", "search", "look up"]
_TASK_KEYWORDS = ["analyze", "write", "create", "generate", "summarize", "compare"]


async def classify_intent(
    user_input: str,
    history: list[dict],
    llm_client: Any,
    model: str,
) -> str:
    """Classify user intent as chat, task, or tool_use."""
    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_input},
    ]
    try:
        response = await llm_client.chat(messages=messages, model=model)
        raw = (response.content or "").strip().lower()
        # Extract first token (word) instead of requiring exact match
        first_token = re.split(r"[\s\n]+", raw)[0] if raw else ""
        if first_token in ("chat", "task", "tool_use"):
            return first_token
    except Exception:
        pass

    # Heuristic fallback
    text = user_input.lower()
    if any(kw in text for kw in _TOOL_KEYWORDS):
        return "tool_use"
    if any(kw in text for kw in _TASK_KEYWORDS):
        return "task"
    return "chat"
