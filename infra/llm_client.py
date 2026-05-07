from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


def _is_retryable(exc: BaseException) -> bool:
    """Return True if the exception is transient and should be retried.

    Retries on rate-limit, timeout, connection, and generic errors.
    Does NOT retry on authentication/authorization errors.
    """
    try:
        from openai import AuthenticationError as OpenAIAuthError
        if isinstance(exc, OpenAIAuthError):
            return False
    except ImportError:
        pass
    try:
        from openai import PermissionDeniedError as OpenAIPermError
        if isinstance(exc, OpenAIPermError):
            return False
    except ImportError:
        pass
    try:
        from anthropic import AuthenticationError as AnthropicAuthError
        if isinstance(exc, AnthropicAuthError):
            return False
    except ImportError:
        pass
    try:
        from anthropic import PermissionDeniedError as AnthropicPermError
        if isinstance(exc, AnthropicPermError):
            return False
    except ImportError:
        pass
    return True


@dataclass
class ToolCall:
    name: str
    arguments: dict
    id: str | None = None


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
        self._retry_config = config.get("retry", {})
        self._routing_config = config.get("routing", {})

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

    def _resolve_provider_config(self, model: str) -> tuple[str, dict, str]:
        """Find provider config for a given model. Returns (protocol, provider_config, provider_name)."""
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

        protocol = provider_config.get("protocol")
        if not protocol:
            raise ValueError(f"Provider '{provider_name}' missing 'protocol' in config")
        base_url = provider_config.get("base_url")
        if not base_url:
            raise ValueError(f"Provider '{provider_name}' missing 'base_url' in config")
        return protocol, provider_config, provider_name

    async def _call_provider(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None,
    ) -> LLMResponse:
        """Single provider call (no retry). Used as the retry target."""
        protocol, provider_config, provider_name = self._resolve_provider_config(model)

        api_key_env = provider_config.get("api_key_env")
        if not api_key_env:
            raise ValueError(
                f"Provider '{provider_name}' missing 'api_key_env' in config"
            )
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            raise ValueError(
                f"API key not found: set the {api_key_env} environment variable"
            )
        base_url = provider_config.get("base_url")
        if not base_url:
            raise ValueError(
                f"Provider '{provider_name}' missing 'base_url' in config"
            )

        provider = self._get_provider(protocol)
        return await provider.chat(
            messages=messages,
            model=model,
            tools=tools,
            base_url=base_url,
            api_key=api_key,
        )

    async def chat(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Chat with retry + fallback model support."""
        max_retries = self._retry_config.get("max_retries", 3)
        base_delay = self._retry_config.get("base_delay", 1.0)
        max_delay = self._retry_config.get("max_delay", 30.0)

        @retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=base_delay, min=base_delay, max=max_delay),
            reraise=True,
        )
        async def _chat_with_retry(msgs, mdl, tls):
            return await self._call_provider(msgs, mdl, tls)

        try:
            return await _chat_with_retry(messages, model, tools)
        except Exception:
            # Try fallback model if configured
            fallback = self._routing_config.get("fallback_model")
            if fallback and fallback != model:
                return await self._call_provider(messages, fallback, tools)
            raise
