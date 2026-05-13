from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, AsyncIterator

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


def _get_retryable_errors() -> tuple[type[BaseException], ...]:
    """Lazily resolve SDK exception types that are transient and should be retried.

    Returns a tuple of exception classes for rate-limit, timeout, and connection errors
    from both OpenAI and Anthropic SDKs, plus stdlib equivalents.
    """
    errors: list[type[BaseException]] = [ConnectionError, TimeoutError]

    try:
        from openai import RateLimitError, APITimeoutError, APIConnectionError
        errors.extend([RateLimitError, APITimeoutError, APIConnectionError])
        # Include 5xx server errors (retryable)
        try:
            from openai import InternalServerError as OpenAI5xx
            errors.append(OpenAI5xx)
        except ImportError:
            pass
    except ImportError:
        pass

    try:
        from anthropic import RateLimitError, APITimeoutError, APIConnectionError
        errors.extend([RateLimitError, APITimeoutError, APIConnectionError])
        # Include 5xx server errors (retryable)
        try:
            from anthropic import InternalServerError as Anthropic5xx
            errors.append(Anthropic5xx)
        except ImportError:
            pass
    except ImportError:
        pass

    return tuple(errors)


def _is_retryable(exc: BaseException) -> bool:
    """Check if an exception is retryable (transient errors only).

    For status-based errors, retry 5xx (server errors) and known retryable types
    (rate limit, timeout, connection). Do NOT retry 4xx client errors (auth, bad request).
    """
    # First check if the exception type is in our explicit retryable list
    if isinstance(exc, _get_retryable_errors()):
        return True
    # For status-based errors not in the list, only retry 5xx
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return 500 <= status_code < 600
    return False


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
    reasoning_content: str = ""  # DeepSeek thinking 模式返回的推理内容


class LLMClient:
    """Unified LLM calling entry point."""

    def __init__(self, config: dict):
        self._providers_config = config.get("providers", {})
        self._providers: dict = {}
        self._retry_config = config.get("retry", {})
        self._routing_config = config.get("routing", {})
        self._models = config.get("models", [])

    def _get_provider(self, protocol: str, base_url: str, api_key: str, enable_thinking: bool = True):
        cache_key = (protocol, base_url)
        if cache_key not in self._providers:
            if protocol == "openai":
                from infra.providers.openai_compat import OpenAICompatProvider
                self._providers[cache_key] = OpenAICompatProvider(base_url, api_key)
            elif protocol == "anthropic":
                from infra.providers.anthropic_compat import AnthropicCompatProvider
                self._providers[cache_key] = AnthropicCompatProvider(base_url, api_key, enable_thinking=enable_thinking)
            else:
                raise ValueError(f"Unknown protocol: {protocol}")
        return self._providers[cache_key]

    async def close(self):
        """Close all cached provider HTTP clients."""
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()

    def _resolve_provider_config(self, model: str) -> tuple[str, dict, str]:
        """Find provider config for a given model. Returns (protocol, provider_config, provider_name)."""
        from config.model_registry import ModelRegistry

        registry = ModelRegistry({"models": self._models, "routing": self._routing_config})
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

    @staticmethod
    def _api_model_id(model: str, provider_name: str) -> str:
        """Strip local provider prefix to get the actual API model name.

        Config IDs like 'minimax/MiniMax-M2.7' use the prefix for local routing;
        the API only receives 'MiniMax-M2.7'.
        """
        prefix = provider_name + "/"
        if model.startswith(prefix):
            return model[len(prefix):]
        return model

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

        enable_thinking = provider_config.get("enable_thinking", True)
        provider = self._get_provider(protocol, base_url, api_key, enable_thinking=enable_thinking)
        api_model = self._api_model_id(model, provider_name)
        return await provider.chat(
            messages=messages,
            model=api_model,
            tools=tools,
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
        except Exception as exc:
            # Try fallback model if configured (only for transient/retryable errors)
            if not _is_retryable(exc):
                raise
            fallback = self._routing_config.get("fallback_model")
            if fallback and fallback != model:
                return await self._call_provider(messages, fallback, tools)
            raise

    async def chat_stream(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream chat completions, delegating to the provider's chat_stream().

        Yields event dicts from the underlying provider.
        """
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

        enable_thinking = provider_config.get("enable_thinking", True)
        provider = self._get_provider(protocol, base_url, api_key, enable_thinking=enable_thinking)
        api_model = self._api_model_id(model, provider_name)
        async for event in provider.chat_stream(
            messages=messages,
            model=api_model,
            tools=tools,
        ):
            yield event
