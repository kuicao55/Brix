"""Intent classification using LLM."""

from __future__ import annotations

import re
import time
from typing import Any

INTENT_SYSTEM_PROMPT = (
    "You are an intent classifier. "
    "Given the user message, classify it as one of: chat, task, tool_use. "
    "Respond with ONLY one of those three words."
)

_TOOL_KEYWORDS = ["weather", "calculate", "read file", "search", "look up"]
_TASK_KEYWORDS = ["analyze", "write", "create", "generate", "summarize", "compare"]


def _summarize_msgs(messages: list[dict]) -> list[dict]:
    """Return a compact summary of messages for logging."""
    result = []
    for m in messages:
        entry: dict = {"role": m.get("role", "?")}
        content = m.get("content", "")
        if isinstance(content, str):
            entry["content"] = content
        elif isinstance(content, list):
            # Anthropic-style content blocks
            entry["content"] = [
                {k: v for k, v in block.items() if k != "input"}
                if block.get("type") == "tool_use" else block
                for block in content
            ]
        result.append(entry)
    return result


async def classify_intent(
    user_input: str,
    history: list[dict],
    llm_client: Any,
    model: str,
    hooks: Any = None,
) -> str:
    """Classify user intent as chat, task, or tool_use."""
    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_input},
    ]

    t0 = time.monotonic()

    try:
        response = await llm_client.chat(messages=messages, model=model)
        raw_content = response.content or ""
        first_token = re.split(r"[\s\n]+", raw_content.strip().lower())[0] if raw_content.strip() else ""
        if first_token in ("chat", "task", "tool_use"):
            elapsed = int((time.monotonic() - t0) * 1000)
            if hooks:
                hooks.fire("intent", result=first_token, via="llm",
                           model=model, response=raw_content.strip(),
                           ms=elapsed, prompt_msgs=len(messages),
                           prompt=_summarize_msgs(messages))
            return first_token
    except Exception:
        pass

    # Heuristic fallback
    text = user_input.lower()
    if any(kw in text for kw in _TOOL_KEYWORDS):
        result = "tool_use"
    elif any(kw in text for kw in _TASK_KEYWORDS):
        result = "task"
    else:
        result = "chat"

    elapsed = int((time.monotonic() - t0) * 1000)
    if hooks:
        hooks.fire("intent", result=result, via="heuristic",
                   model=model,
                   ms=elapsed, prompt_msgs=len(messages),
                   prompt=_summarize_msgs(messages))
    return result
