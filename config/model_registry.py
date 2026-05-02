from __future__ import annotations


class ModelRegistry:
    """Provides model lookup by id, purpose, cost_tier."""

    def __init__(self, config: dict):
        self._models = config.get("models", [])
        self._routing = config.get("routing", {})

    def get_model_by_id(self, model_id: str) -> dict | None:
        for model in self._models:
            if model["id"] == model_id:
                return model
        return None

    def get_default_model(self) -> dict | None:
        default_id = self._routing.get("default_model")
        if default_id:
            return self.get_model_by_id(default_id)
        for model in self._models:
            if model.get("default"):
                return model
        return None

    def get_fallback_model(self) -> dict | None:
        fallback_id = self._routing.get("fallback_model")
        if fallback_id:
            return self.get_model_by_id(fallback_id)
        return self.get_default_model()

    def get_models_by_purpose(self, purpose: str) -> list[dict]:
        return [m for m in self._models if purpose in m.get("purpose", [])]
