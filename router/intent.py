"""Intent classification using LLM."""

from __future__ import annotations

from typing import Any

INTENT_SYSTEM_PROMPT = (
    "You are an intent classifier. "
    "Given the user message, classify it as one of: chat, task, tool_use. "
    "Respond with ONLY one of those three words."
)


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
        if raw in ("chat", "task", "tool_use"):
            return raw
        return "chat"
    except Exception:
        return "chat"
