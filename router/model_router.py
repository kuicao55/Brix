"""Model selection based on intent, complexity, and config."""

from __future__ import annotations


def select_model(intent: str, complexity: str, config: dict) -> str:
    """Select the best model for the given intent and complexity.

    Routing priority:
      image/video → dedicated model (image_generation / video_generation purpose)
      code        → coding purpose model
      knowledge   → knowledge purpose model
      deep_chat   → reasoning purpose model (or knowledge if no reasoning)
      tool_use    → tool_calling capable model (default)
      chat        → chat_model config (fast/cheap)
      fallback    → default_model
    """
    routing = config.get("routing", {})
    models = config.get("models", [])

    default_model = routing.get("default_model", "")
    fallback_model = routing.get("fallback_model", default_model)
    chat_model = routing.get("chat_model", "")

    def _find_model_by_purpose(purpose: str) -> str | None:
        for model in models:
            if purpose in model.get("purpose", []):
                return model.get("id")
        return None

    # 生成类 — 专用模型
    if intent == "image":
        return _find_model_by_purpose("image_generation") or fallback_model
    if intent == "video":
        return _find_model_by_purpose("video_generation") or fallback_model

    # 代码
    if intent == "code":
        return _find_model_by_purpose("coding") or fallback_model

    # 知识问题
    if intent == "knowledge":
        return _find_model_by_purpose("knowledge") or _find_model_by_purpose("reasoning") or fallback_model

    # 深度讨论
    if intent == "deep_chat":
        return _find_model_by_purpose("reasoning") or _find_model_by_purpose("complex_qa") or fallback_model

    # 工具调用 — 走 default（通常是有 tool_calling 的主力模型）
    if intent == "tool_use":
        return default_model or fallback_model

    # 闲聊 — 便宜快速
    if intent == "chat":
        if chat_model:
            return chat_model
        return _find_model_by_purpose("fast_chat") or default_model or fallback_model

    # 高复杂度兜底
    if complexity == "high":
        return _find_model_by_purpose("reasoning") or fallback_model

    return default_model or fallback_model
