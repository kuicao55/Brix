"""Model selection based on intent, complexity, and config."""

from __future__ import annotations


def select_model(intent: str, complexity: str, config: dict) -> str:
    """Select the best model for the given intent and complexity.

    Falls back to default_model when no specific match is found.
    """
    routing = config.get("routing", {})
    models = config.get("models", [])

    default_model = routing.get("default_model", "")
    fallback_model = routing.get("fallback_model", default_model)
    chat_model = routing.get("chat_model", "")

    # For high complexity, prefer models with 'reasoning' purpose
    if complexity == "high":
        for model in models:
            purposes = model.get("purpose", [])
            if "reasoning" in purposes:
                return model.get("id", fallback_model)

    # For task intent, prefer models with 'coding' purpose
    if intent == "task":
        for model in models:
            purposes = model.get("purpose", [])
            if "coding" in purposes:
                return model.get("id", fallback_model)

    # For chat intent, use chat_model if configured
    if intent == "chat" and chat_model:
        return chat_model

    return default_model or fallback_model
