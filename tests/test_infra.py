import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from infra.llm_client import LLMClient, LLMResponse, ToolCall


@pytest.fixture
def config():
    return {
        "providers": {
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "protocol": "openai",
            },
            "anthropic": {
                "base_url": "https://api.anthropic.com",
                "api_key_env": "ANTHROPIC_API_KEY",
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
async def test_llm_client_chat_openai(llm_client):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello!"
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].finish_reason = "stop"

    with patch("infra.providers.openai_compat.AsyncOpenAI") as MockClient:
        MockClient.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = await llm_client.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4.1-mini",
            )
            assert isinstance(result, LLMResponse)
            assert result.content == "Hello!"
