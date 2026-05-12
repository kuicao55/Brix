import pytest
from unittest.mock import AsyncMock, MagicMock
from router.intent import classify_intent
from router.complexity import evaluate_complexity
from router.model_router import select_model


# ---------------------------------------------------------------------------
# Fix 3: Robust intent parsing tests
# ---------------------------------------------------------------------------

class TestClassifyIntentRobust:
    async def test_extra_whitespace_parsing(self):
        """LLM responses with extra whitespace should still classify correctly."""
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content="  tool_use  \n", tool_calls=[], finish_reason="stop")
        result = await classify_intent("What's the weather?", [], mock_llm, "gpt-4.1-mini")
        assert result == "tool_use"

    async def test_uppercase_response(self):
        """LLM responses in uppercase should be handled."""
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content="CODE", tool_calls=[], finish_reason="stop")
        result = await classify_intent("Write a function", [], mock_llm, "gpt-4.1-mini")
        assert result == "code"

    async def test_response_with_trailing_text(self):
        """Only the first token of the LLM response should be used."""
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content="chat because it's a greeting", tool_calls=[], finish_reason="stop")
        result = await classify_intent("Hello!", [], mock_llm, "gpt-4.1-mini")
        assert result == "chat"

    async def test_heuristic_fallback_tool_use(self):
        """When LLM returns garbage, tool keywords should trigger tool_use."""
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content="I don't know", tool_calls=[], finish_reason="stop")
        result = await classify_intent("What's the weather in Tokyo?", [], mock_llm, "gpt-4.1-mini")
        assert result == "tool_use"

    async def test_heuristic_fallback_deep_chat(self):
        """When LLM returns garbage, deep keywords should trigger deep_chat."""
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content="hmm", tool_calls=[], finish_reason="stop")
        result = await classify_intent("Please analyze this document", [], mock_llm, "gpt-4.1-mini")
        assert result == "deep_chat"

    async def test_heuristic_fallback_chat(self):
        """When LLM returns garbage and no keywords match, default to chat."""
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content="???invalid", tool_calls=[], finish_reason="stop")
        result = await classify_intent("Hello, how are you?", [], mock_llm, "gpt-4.1-mini")
        assert result == "chat"

    async def test_exception_triggers_heuristic(self):
        """When LLM raises, heuristic should still classify."""
        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = RuntimeError("API down")
        result = await classify_intent("calculate 2+2", [], mock_llm, "gpt-4.1-mini")
        assert result == "tool_use"


# ---------------------------------------------------------------------------
# Existing tests (kept intact)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_intent_chat():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = MagicMock(content="chat", tool_calls=[], finish_reason="stop")
    result = await classify_intent("Hello, how are you?", [], mock_llm, "gpt-4.1-mini")
    assert result in ["chat", "deep_chat", "knowledge", "code", "tool_use", "image", "video"]


def test_complexity_low():
    result = evaluate_complexity("Hello")
    assert result == "low"


def test_complexity_medium():
    result = evaluate_complexity("Can you help me analyze this document and summarize the key points?")
    assert result in ["low", "medium", "high"]


def test_complexity_high():
    result = evaluate_complexity(
        "I need you to read all files in this directory, "
        "analyze the code quality, generate a report, "
        "and then create a summary with recommendations for each file."
    )
    assert result in ["medium", "high"]


def test_select_model_default():
    config = {
        "models": [
            {"id": "gpt-4.1-mini", "provider": "openai", "purpose": ["fast_chat"], "cost_tier": "low"},
            {"id": "gpt-4.1", "provider": "openai", "purpose": ["coding"], "cost_tier": "high"},
        ],
        "routing": {"default_model": "gpt-4.1-mini", "fallback_model": "gpt-4.1-mini"},
    }
    model = select_model("chat", "low", config)
    assert model == "gpt-4.1-mini"


def test_select_model_high_complexity():
    config = {
        "models": [
            {"id": "gpt-4.1-mini", "provider": "openai", "purpose": ["fast_chat"], "cost_tier": "low"},
            {"id": "gpt-4.1", "provider": "openai", "purpose": ["coding", "reasoning"], "cost_tier": "high"},
        ],
        "routing": {"default_model": "gpt-4.1-mini", "fallback_model": "gpt-4.1-mini"},
    }
    model = select_model("task", "high", config)
    assert model in ["gpt-4.1", "gpt-4.1-mini"]
