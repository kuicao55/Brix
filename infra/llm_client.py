from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]
    finish_reason: str


class LLMClient:
    """Unified LLM calling entry point."""

    def __init__(self, config: dict):
        self._providers_config = config.get("providers", {})
        self._providers: dict = {}

    def _get_provider(self, protocol: str):
        if protocol not in self._providers:
            if protocol == "openai":
                from infra.providers.openai_compat import OpenAICompatProvider
                self._providers[protocol] = OpenAICompatProvider()
            elif protocol == "anthropic":
                from infra.providers.anthropic_compat import AnthropicCompatProvider
                self._providers[protocol] = AnthropicCompatProvider()
            else:
                raise ValueError(f"Unknown protocol: {protocol}")
        return self._providers[protocol]

    def _resolve_provider_config(self, model: str) -> tuple[str, dict]:
        """Find provider config for a given model."""
        from config.loader import load_config
        from config.model_registry import ModelRegistry

        config = load_config()
        registry = ModelRegistry(config)
        model_info = registry.get_model_by_id(model)
        if not model_info:
            raise ValueError(f"Model not found: {model}")

        provider_name = model_info["provider"]
        provider_config = self._providers_config.get(provider_name)
        if not provider_config:
            raise ValueError(f"Provider not found: {provider_name}")

        return provider_config["protocol"], provider_config

    async def chat(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        protocol, provider_config = self._resolve_provider_config(model)
        provider = self._get_provider(protocol)

        api_key = os.environ.get(provider_config["api_key_env"], "")
        return await provider.chat(
            messages=messages,
            model=model,
            tools=tools,
            base_url=provider_config["base_url"],
            api_key=api_key,
        )
