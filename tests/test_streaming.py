"""Tests for streaming providers (chat_stream)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infra.llm_client import LLMClient


@pytest.mark.asyncio
async def test_openai_stream_yields_text_delta():
    """OpenAICompatProvider.chat_stream() should yield text_delta dicts."""
    from infra.providers.openai_compat import OpenAICompatProvider

    provider = OpenAICompatProvider()

    # Build mock SSE chunks from the OpenAI streaming API
    mock_chunks = []
    for text in ["Hello", " world", "!"]:
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = text
        chunk.choices[0].delta.tool_calls = None
        mock_chunks.append(chunk)

    # Final chunk with no content (stream end)
    final_chunk = MagicMock()
    final_chunk.choices = [MagicMock()]
    final_chunk.choices[0].delta.content = None
    final_chunk.choices[0].delta.tool_calls = None
    mock_chunks.append(final_chunk)

    async def mock_aiter(*args, **kwargs):
        for chunk in mock_chunks:
            yield chunk

    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_aiter
    mock_client.close = AsyncMock()

    with patch("infra.providers.openai_compat.AsyncOpenAI", return_value=mock_client):
        results = []
        async for event in provider.chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model="test-model",
            tools=None,
            base_url="http://test",
            api_key="sk-test",
        ):
            results.append(event)

    text_deltas = [e for e in results if e["type"] == "text_delta"]
    assert len(text_deltas) == 3
    assert text_deltas[0]["text"] == "Hello"
    assert text_deltas[1]["text"] == " world"
    assert text_deltas[2]["text"] == "!"


@pytest.mark.asyncio
async def test_openai_stream_yields_tool_calls():
    """OpenAICompatProvider.chat_stream() should accumulate tool call deltas."""
    from infra.providers.openai_compat import OpenAICompatProvider

    provider = OpenAICompatProvider()

    # Simulate tool call chunks: index/name first, then arguments in pieces
    tc_delta_1 = MagicMock()
    tc_delta_1.index = 0
    tc_delta_1.id = "call_123"
    tc_delta_1.function.name = "get_weather"
    tc_delta_1.function.arguments = ""

    tc_delta_2 = MagicMock()
    tc_delta_2.index = 0
    tc_delta_2.id = None
    tc_delta_2.function.name = None
    tc_delta_2.function.arguments = '{"loc":'

    tc_delta_3 = MagicMock()
    tc_delta_3.index = 0
    tc_delta_3.id = None
    tc_delta_3.function.name = None
    tc_delta_3.function.arguments = '"Paris"}'

    chunk1 = MagicMock()
    chunk1.choices = [MagicMock()]
    chunk1.choices[0].delta.content = None
    chunk1.choices[0].delta.tool_calls = [tc_delta_1]

    chunk2 = MagicMock()
    chunk2.choices = [MagicMock()]
    chunk2.choices[0].delta.content = None
    chunk2.choices[0].delta.tool_calls = [tc_delta_2]

    chunk3 = MagicMock()
    chunk3.choices = [MagicMock()]
    chunk3.choices[0].delta.content = None
    chunk3.choices[0].delta.tool_calls = [tc_delta_3]

    # Final chunk
    final_chunk = MagicMock()
    final_chunk.choices = [MagicMock()]
    final_chunk.choices[0].delta.content = None
    final_chunk.choices[0].delta.tool_calls = None

    mock_chunks = [chunk1, chunk2, chunk3, final_chunk]

    async def mock_aiter(*args, **kwargs):
        for chunk in mock_chunks:
            yield chunk

    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_aiter
    mock_client.close = AsyncMock()

    with patch("infra.providers.openai_compat.AsyncOpenAI", return_value=mock_client):
        results = []
        async for event in provider.chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model="test-model",
            tools=[{"type": "function", "function": {"name": "get_weather"}}],
            base_url="http://test",
            api_key="sk-test",
        ):
            results.append(event)

    tool_calls = [e for e in results if e["type"] == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "get_weather"
    assert tool_calls[0]["arguments"] == {"loc": "Paris"}
    assert tool_calls[0]["id"] == "call_123"


@pytest.mark.asyncio
async def test_anthropic_stream_yields_text_delta():
    """AnthropicCompatProvider.chat_stream() should yield text_delta dicts."""
    from infra.providers.anthropic_compat import AnthropicCompatProvider

    provider = AnthropicCompatProvider()

    # Mock chunks that the async iterator would yield
    content_block_start = MagicMock()
    content_block_start.type = "content_block_start"
    content_block_start.index = 0

    delta_event_1 = MagicMock()
    delta_event_1.type = "content_block_delta"
    delta_event_1.delta = MagicMock()
    delta_event_1.delta.type = "text_delta"
    delta_event_1.delta.text = "Hello"

    delta_event_2 = MagicMock()
    delta_event_2.type = "content_block_delta"
    delta_event_2.delta = MagicMock()
    delta_event_2.delta.type = "text_delta"
    delta_event_2.delta.text = " world"

    content_block_stop = MagicMock()
    content_block_stop.type = "content_block_stop"

    message_stop = MagicMock()
    message_stop.type = "message_stop"

    mock_events = [content_block_start, delta_event_1, delta_event_2, content_block_stop, message_stop]

    async def mock_aiter(self):
        for event in mock_events:
            yield event

    # Mock the final message
    final_message = MagicMock()
    final_message.content = []
    final_message.stop_reason = "end_turn"

    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=False)
    mock_stream.__aiter__ = mock_aiter
    mock_stream.get_final_message = AsyncMock(return_value=final_message)

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = mock_stream
    mock_client.close = AsyncMock()

    with patch("infra.providers.anthropic_compat.AsyncAnthropic", return_value=mock_client):
        results = []
        async for event in provider.chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model="test-model",
            tools=None,
            base_url="http://test",
            api_key="sk-test",
        ):
            results.append(event)

    text_deltas = [e for e in results if e["type"] == "text_delta"]
    assert len(text_deltas) == 2
    assert text_deltas[0]["text"] == "Hello"
    assert text_deltas[1]["text"] == " world"


@pytest.mark.asyncio
async def test_llm_client_chat_stream():
    """LLMClient.chat_stream() should delegate to provider.chat_stream()."""
    mock_provider = MagicMock()

    async def mock_stream(*args, **kwargs):
        yield {"type": "text_delta", "text": "hi"}
        yield {"type": "text_delta", "text": " there"}

    mock_provider.chat_stream = mock_stream

    config = {
        "providers": {
            "test": {
                "protocol": "openai",
                "base_url": "http://test",
                "api_key_env": "TEST_KEY",
            }
        }
    }
    client = LLMClient(config)

    with patch.object(client, "_get_provider", return_value=mock_provider), \
         patch.object(
             client,
             "_resolve_provider_config",
             return_value=(
                 "openai",
                 {
                     "protocol": "openai",
                     "base_url": "http://test",
                     "api_key_env": "TEST_KEY",
                 },
                 "test",
             ),
         ), \
         patch.dict("os.environ", {"TEST_KEY": "sk-test"}):
        results = []
        async for event in client.chat_stream(
            [{"role": "user", "content": "hi"}], "test-model"
        ):
            results.append(event)

        assert len(results) == 2
        assert results[0]["text"] == "hi"
        assert results[1]["text"] == " there"
