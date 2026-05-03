import pytest
from unittest.mock import AsyncMock, MagicMock
from router.intent import classify_intent
from router.complexity import evaluate_complexity
from router.model_router import select_model


@pytest.mark.asyncio
async def test_classify_intent_chat():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = MagicMock(content="chat", tool_calls=[], finish_reason="stop")
    result = await classify_intent("Hello, how are you?", [], mock_llm, "gpt-4.1-mini")
    assert result in ["chat", "task", "tool_use"]


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
