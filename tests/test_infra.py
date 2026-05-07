import os

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from infra.llm_client import LLMClient, LLMResponse, ToolCall


@pytest.fixture
def config():
    return {
        "providers": {
            "zenmux-openai": {
                "base_url": "https://zenmux.ai/api/v1",
                "api_key_env": "ZENMUX_API_KEY",
                "protocol": "openai",
            },
            "zenmux-anthropic": {
                "base_url": "https://zenmux.ai/api/anthropic",
                "api_key_env": "ZENMUX_API_KEY",
                "protocol": "anthropic",
            },
            "minimax": {
                "base_url": "https://api.minimaxi.com/anthropic",
                "api_key_env": "MINIMAX_API_KEY",
                "protocol": "anthropic",
            },
            "mimo": {
                "base_url": "https://api.xiaomimimo.com/anthropic",
                "api_key_env": "MIMO_API_KEY",
                "protocol": "anthropic",
            },
        }
    }


@pytest.fixture
def llm_client(config):
    return LLMClient(config)


def test_llm_response_structure():
    resp = LLMResponse(content="hello", tool_calls=[], finish_reason="stop")
    assert resp.content == "hello"
    assert resp.tool_calls == []
    assert resp.finish_reason == "stop"


def test_tool_call_structure():
    tc = ToolCall(name="weather", arguments={"city": "Tokyo"})
    assert tc.name == "weather"
    assert tc.arguments == {"city": "Tokyo"}


def test_llm_client_selects_openai_provider(llm_client):
    provider = llm_client._get_provider("openai")
    assert provider.__class__.__name__ == "OpenAICompatProvider"


def test_llm_client_selects_anthropic_provider(llm_client):
    provider = llm_client._get_provider("anthropic")
    assert provider.__class__.__name__ == "AnthropicCompatProvider"


@pytest.mark.asyncio
async def test_llm_client_chat_missing_protocol_raises(llm_client):
    """chat() should raise when provider config is missing 'protocol'."""
    bad_config = {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
    }
    with patch.object(
        llm_client,
        "_resolve_provider_config",
        side_effect=ValueError("Provider 'openai' missing 'protocol' in config"),
    ):
        with pytest.raises(ValueError, match="missing 'protocol'"):
            await llm_client.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4.1-mini",
            )


@pytest.mark.asyncio
async def test_llm_client_chat_missing_base_url_raises(llm_client):
    """chat() should raise when provider config is missing 'base_url'."""
    bad_config = {
        "protocol": "openai",
        "api_key_env": "OPENAI_API_KEY",
    }
    with patch.object(
        llm_client,
        "_resolve_provider_config",
        return_value=("openai", bad_config, "openai"),
    ):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with pytest.raises(ValueError, match="missing 'base_url'"):
                await llm_client.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gpt-4.1-mini",
                )


@pytest.mark.asyncio
async def test_llm_client_chat_openai(llm_client):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello!"
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].finish_reason = "stop"

    with patch("infra.providers.openai_compat.AsyncOpenAI") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_instance.close = AsyncMock()
        with patch.dict("os.environ", {"ZENMUX_API_KEY": "test-key"}):
            result = await llm_client.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="zenmux-openai/google/gemini-3.1-pro-preview",
            )
            assert isinstance(result, LLMResponse)
            assert result.content == "Hello!"


# --- Fix 1: API key validation ---


@pytest.mark.asyncio
async def test_llm_client_chat_empty_api_key_raises(llm_client):
    """chat() should raise a clear error when API key env var is empty."""
    with patch.dict("os.environ", {"ZENMUX_API_KEY": ""}):
        with pytest.raises(ValueError, match="API key"):
            await llm_client.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="zenmux-openai/google/gemini-3.1-pro-preview",
            )


@pytest.mark.asyncio
async def test_llm_client_chat_unset_api_key_raises(llm_client):
    """chat() should raise a clear error when API key env var is unset."""
    env = os.environ.copy()
    env.pop("ZENMUX_API_KEY", None)
    with patch.dict("os.environ", env, clear=True):
        with pytest.raises(ValueError, match="API key"):
            await llm_client.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="zenmux-openai/google/gemini-3.1-pro-preview",
            )


@pytest.mark.asyncio
async def test_llm_client_chat_missing_api_key_env_config(llm_client):
    """chat() should raise a clear error when provider config lacks 'api_key_env'."""
    # Provider config without api_key_env
    bad_provider_config = {
        "base_url": "https://api.openai.com/v1",
        "protocol": "openai",
    }
    with patch.object(
        llm_client,
        "_resolve_provider_config",
        return_value=("openai", bad_provider_config, "openai"),
    ):
        with pytest.raises(ValueError, match="missing 'api_key_env'"):
            await llm_client.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="some-model",
            )


# --- Fix 2: JSON parsing guard ---


@pytest.mark.asyncio
async def test_openai_provider_handles_invalid_json_tool_args():
    """Provider should handle invalid JSON in tool call arguments gracefully."""
    from infra.providers.openai_compat import OpenAICompatProvider

    mock_tc = MagicMock()
    mock_tc.function.name = "test_func"
    mock_tc.function.arguments = "not valid json{"

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = ""
    mock_response.choices[0].message.tool_calls = [mock_tc]
    mock_response.choices[0].finish_reason = "stop"

    provider = OpenAICompatProvider()
    with patch("infra.providers.openai_compat.AsyncOpenAI") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_instance.close = AsyncMock()
        result = await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            model="test",
            tools=[{"type": "function", "function": {"name": "test_func"}}],
            base_url="http://test",
            api_key="test-key",
        )
        assert isinstance(result, LLMResponse)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "test_func"
        # Fallback: arguments should be a dict with the raw string
        assert isinstance(result.tool_calls[0].arguments, dict)


@pytest.mark.asyncio
async def test_openai_provider_handles_non_dict_json_tool_args():
    """Provider should handle valid JSON that parses to a non-dict (e.g. list)."""
    from infra.providers.openai_compat import OpenAICompatProvider

    mock_tc = MagicMock()
    mock_tc.function.name = "test_func"
    mock_tc.function.arguments = "[1, 2, 3]"

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = ""
    mock_response.choices[0].message.tool_calls = [mock_tc]
    mock_response.choices[0].finish_reason = "stop"

    provider = OpenAICompatProvider()
    with patch("infra.providers.openai_compat.AsyncOpenAI") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_instance.close = AsyncMock()
        result = await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            model="test",
            tools=[{"type": "function", "function": {"name": "test_func"}}],
            base_url="http://test",
            api_key="test-key",
        )
        assert isinstance(result, LLMResponse)
        assert len(result.tool_calls) == 1
        # Non-dict JSON should fallback to {"raw": original_string}
        assert result.tool_calls[0].arguments == {"raw": "[1, 2, 3]"}


@pytest.mark.asyncio
async def test_openai_provider_handles_preparsed_dict_tool_args():
    """Provider should use pre-parsed dict arguments directly, not wrap under 'raw'."""
    from infra.providers.openai_compat import OpenAICompatProvider

    parsed_args = {"city": "Tokyo", "unit": "celsius"}
    mock_tc = MagicMock()
    mock_tc.function.name = "test_func"
    mock_tc.function.arguments = parsed_args  # already a dict, not a JSON string

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = ""
    mock_response.choices[0].message.tool_calls = [mock_tc]
    mock_response.choices[0].finish_reason = "stop"

    provider = OpenAICompatProvider()
    with patch("infra.providers.openai_compat.AsyncOpenAI") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_instance.close = AsyncMock()
        result = await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            model="test",
            tools=[{"type": "function", "function": {"name": "test_func"}}],
            base_url="http://test",
            api_key="test-key",
        )
        assert isinstance(result, LLMResponse)
        assert len(result.tool_calls) == 1
        # Should be the original dict, not {"raw": {...}}
        assert result.tool_calls[0].arguments == {"city": "Tokyo", "unit": "celsius"}


# --- Fix 3: Client lifecycle ---


@pytest.mark.asyncio
async def test_openai_provider_closes_client():
    """OpenAI provider should close the client after use."""
    from infra.providers.openai_compat import OpenAICompatProvider

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "hi"
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].finish_reason = "stop"

    provider = OpenAICompatProvider()
    with patch("infra.providers.openai_compat.AsyncOpenAI") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_instance.close = AsyncMock()

        await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            model="test",
            tools=None,
            base_url="http://test",
            api_key="test-key",
        )
        mock_instance.close.assert_called_once()


@pytest.mark.asyncio
async def test_anthropic_provider_closes_client():
    """Anthropic provider should close the client after use."""
    from infra.providers.anthropic_compat import AnthropicCompatProvider

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "hi"

    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_response.stop_reason = "stop"

    provider = AnthropicCompatProvider()
    with patch("infra.providers.anthropic_compat.AsyncAnthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_instance.close = AsyncMock()

        await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            model="test",
            tools=None,
            base_url="http://test",
            api_key="test-key",
        )
        mock_instance.close.assert_called_once()


# --- Fix 4: Anthropic adapter test ---


@pytest.mark.asyncio
async def test_anthropic_provider_chat():
    """AnthropicCompatProvider.chat() handles system msg, tool conversion, tool_use parsing."""
    from infra.providers.anthropic_compat import AnthropicCompatProvider

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Hello from Claude!"

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "get_weather"
    tool_block.input = {"city": "Tokyo"}

    mock_response = MagicMock()
    mock_response.content = [text_block, tool_block]
    mock_response.stop_reason = "tool_use"

    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a city",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
        },
    }]

    provider = AnthropicCompatProvider()
    with patch("infra.providers.anthropic_compat.AsyncAnthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_instance.close = AsyncMock()

        result = await provider.chat(
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "What's the weather in Tokyo?"},
            ],
            model="claude-sonnet-4-20250514",
            tools=tools,
            base_url="http://test",
            api_key="test-key",
        )

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello from Claude!"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_weather"
        assert result.tool_calls[0].arguments == {"city": "Tokyo"}
        assert result.finish_reason == "tool_use"

        # Verify system message was extracted and passed separately
        call_kwargs = mock_instance.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are helpful."
        assert all(m["role"] != "system" for m in call_kwargs["messages"])

        # Verify tools were converted to Anthropic format
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["name"] == "get_weather"
        assert call_kwargs["tools"][0]["description"] == "Get weather for a city"
        assert "input_schema" in call_kwargs["tools"][0]


# --- Phase 1 dependency imports ---


def test_phase1_dependencies_importable():
    """Verify Phase 1 dependencies are installed."""
    import tenacity
    import tiktoken
    import rich

    assert hasattr(tenacity, "retry")
    assert hasattr(tiktoken, "encoding_for_model")
    assert hasattr(rich, "print")


# --- Fix 5: Retry with tenacity ---


@pytest.mark.asyncio
async def test_retry_on_transient_error():
    """LLMClient.chat() should retry on transient errors."""
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        side_effect=[
            Exception("rate_limit"),  # first attempt
            Exception("rate_limit"),  # second attempt
            LLMResponse(content="ok", tool_calls=[], finish_reason="stop"),  # third succeeds
        ]
    )

    config = {
        "providers": {
            "test-provider": {
                "protocol": "openai",
                "base_url": "http://test",
                "api_key_env": "TEST_KEY",
            }
        }
    }
    client = LLMClient(config)

    with patch.object(client, "_get_provider", return_value=mock_provider), \
         patch.object(client, "_resolve_provider_config", return_value=(
             "openai", {"protocol": "openai", "base_url": "http://test", "api_key_env": "TEST_KEY"}, "test"
         )), \
         patch.dict("os.environ", {"TEST_KEY": "sk-test"}):
        response = await client.chat([{"role": "user", "content": "hi"}], "test-model")
        assert response.content == "ok"
        assert mock_provider.chat.call_count == 3


@pytest.mark.asyncio
async def test_retry_fallback_model():
    """After exhausting retries, try fallback_model."""
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        side_effect=[
            Exception("rate_limit"),
            Exception("rate_limit"),
            Exception("rate_limit"),  # 3 failures on primary
            LLMResponse(content="fallback ok", tool_calls=[], finish_reason="stop"),  # fallback succeeds
        ]
    )

    config = {
        "providers": {
            "test-provider": {
                "protocol": "openai",
                "base_url": "http://test",
                "api_key_env": "TEST_KEY",
            }
        },
        "routing": {
            "fallback_model": "test/fallback-model",
        },
    }
    client = LLMClient(config)

    with patch.object(client, "_get_provider", return_value=mock_provider), \
         patch.object(client, "_resolve_provider_config", return_value=(
             "openai", {"protocol": "openai", "base_url": "http://test", "api_key_env": "TEST_KEY"}, "test"
         )), \
         patch.dict("os.environ", {"TEST_KEY": "sk-test"}):
        response = await client.chat([{"role": "user", "content": "hi"}], "test-model")
        assert response.content == "fallback ok"


@pytest.mark.asyncio
async def test_no_retry_on_auth_error():
    """Auth errors (401/403) should not be retried."""
    from openai import AuthenticationError

    mock_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"error": {"message": "invalid key"}}
    mock_provider.chat = AsyncMock(
        side_effect=AuthenticationError(
            message="invalid key",
            response=mock_response,
            body={"error": {"message": "invalid key"}},
        )
    )

    config = {
        "providers": {
            "test-provider": {
                "protocol": "openai",
                "base_url": "http://test",
                "api_key_env": "TEST_KEY",
            }
        }
    }
    client = LLMClient(config)

    with patch.object(client, "_get_provider", return_value=mock_provider), \
         patch.object(client, "_resolve_provider_config", return_value=(
             "openai", {"protocol": "openai", "base_url": "http://test", "api_key_env": "TEST_KEY"}, "test"
         )), \
         patch.dict("os.environ", {"TEST_KEY": "sk-test"}):
        with pytest.raises(AuthenticationError):
            await client.chat([{"role": "user", "content": "hi"}], "test-model")
        # Should only be called once — no retry
        assert mock_provider.chat.call_count == 1
