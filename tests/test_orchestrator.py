"""Tests for the orchestrator state machine engine (Task 3).

TDD: These tests are written BEFORE the implementation.
Step 2 (RED): all should fail with ImportError / ModuleNotFoundError.
Step 4 (GREEN): all should pass after implementation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from infra.llm_client import LLMResponse, ToolCall


# ---------------------------------------------------------------------------
# Test 1: OrchestratorState enum
# ---------------------------------------------------------------------------


def test_states_enum():
    """OrchestratorState enum must expose the five required states."""
    from orchestrator.states import OrchestratorState

    assert OrchestratorState.IDLE == "idle"
    assert OrchestratorState.PLANNING == "planning"
    assert OrchestratorState.EXECUTING == "executing"
    assert OrchestratorState.REVIEWING == "reviewing"
    assert OrchestratorState.RESPONDING == "responding"

    # Enum should have exactly 5 members
    assert len(OrchestratorState) == 5


# ---------------------------------------------------------------------------
# Test 2: OrchestratorContext dataclass
# ---------------------------------------------------------------------------


def test_orchestrator_context():
    """OrchestratorContext holds history, memory, tool_runner, llm_client, model."""
    from orchestrator.engine import OrchestratorContext

    mock_llm = MagicMock()
    mock_runner = MagicMock()

    ctx = OrchestratorContext(
        history=[{"role": "user", "content": "hello"}],
        memory={"key": "val"},
        tool_runner=mock_runner,
        llm_client=mock_llm,
        model="gpt-4.1-mini",
    )

    assert ctx.history == [{"role": "user", "content": "hello"}]
    assert ctx.memory == {"key": "val"}
    assert ctx.tool_runner is mock_runner
    assert ctx.llm_client is mock_llm
    assert ctx.model == "gpt-4.1-mini"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(llm_client, tool_runner=None):
    """Build a minimal OrchestratorContext with mocked dependencies."""
    from orchestrator.engine import OrchestratorContext

    if tool_runner is None:
        tool_runner = AsyncMock()
        tool_runner.run = AsyncMock(return_value=[])

    return OrchestratorContext(
        history=[],
        memory={},
        tool_runner=tool_runner,
        llm_client=llm_client,
        model="test-model",
    )


# ---------------------------------------------------------------------------
# Test 3: Simple chat — LLM responds directly, no tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_simple_chat_no_tools():
    """When the LLM returns no tool_calls the orchestrator responds immediately."""
    from orchestrator.state_machine import StateMachineOrchestrator

    llm = AsyncMock()
    llm.chat = AsyncMock(
        return_value=LLMResponse(
            content="Hello! How can I help?",
            tool_calls=[],
            finish_reason="stop",
        )
    )

    ctx = _make_context(llm)
    orchestrator = StateMachineOrchestrator()
    result = await orchestrator.run("hi", ctx)

    assert result == "Hello! How can I help?"
    # LLM should be called exactly once (single planning pass)
    assert llm.chat.call_count == 1


# ---------------------------------------------------------------------------
# Test 4: Tool-calling loop — LLM requests a tool, then responds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_calling_loop():
    """LLM requests a tool call on first pass, gets result, then responds."""
    from orchestrator.state_machine import StateMachineOrchestrator

    tool_call = ToolCall(name="get_weather", arguments={"city": "Tokyo"})
    first_response = LLMResponse(
        content="",
        tool_calls=[tool_call],
        finish_reason="tool_calls",
    )
    second_response = LLMResponse(
        content="The weather in Tokyo is sunny.",
        tool_calls=[],
        finish_reason="stop",
    )

    llm = AsyncMock()
    llm.chat = AsyncMock(side_effect=[first_response, second_response])

    mock_runner = AsyncMock()
    mock_runner.run = AsyncMock(return_value='{"tool": "get_weather", "result": "sunny"}')

    ctx = _make_context(llm, tool_runner=mock_runner)
    orchestrator = StateMachineOrchestrator()
    result = await orchestrator.run("weather in Tokyo?", ctx)

    assert result == "The weather in Tokyo is sunny."
    # LLM called twice: planning + re-planning after tool execution
    assert llm.chat.call_count == 2
    # Tool runner was called once with the tool call
    mock_runner.run.assert_called_once_with("get_weather", {"city": "Tokyo"})


# ---------------------------------------------------------------------------
# Test 5: Max-iteration guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_iteration_guard():
    """Orchestrator stops after max_iterations even if LLM keeps requesting tools."""
    from orchestrator.state_machine import StateMachineOrchestrator

    tool_call = ToolCall(name="search", arguments={"q": "test"})
    always_tool_response = LLMResponse(
        content="",
        tool_calls=[tool_call],
        finish_reason="tool_calls",
    )

    llm = AsyncMock()
    llm.chat = AsyncMock(return_value=always_tool_response)

    mock_runner = AsyncMock()
    mock_runner.run = AsyncMock(return_value='{"tool": "search", "result": "data"}')

    ctx = _make_context(llm, tool_runner=mock_runner)
    orchestrator = StateMachineOrchestrator(max_iterations=3)
    result = await orchestrator.run("search forever", ctx)

    # Should have stopped after 3 planning calls
    assert llm.chat.call_count == 3
    # Result should be a fallback / last-resort message (not crash)
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# Test 6: Tool execution error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_execution_error():
    """Orchestrator handles tool execution errors gracefully."""
    from orchestrator.state_machine import StateMachineOrchestrator

    tool_call = ToolCall(name="failing_tool", arguments={})
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value=LLMResponse(
        content="", tool_calls=[tool_call], finish_reason="tool_calls"
    ))

    mock_runner = AsyncMock()
    mock_runner.run = AsyncMock(side_effect=RuntimeError("tool broke"))

    ctx = _make_context(llm, tool_runner=mock_runner)
    orchestrator = StateMachineOrchestrator()
    result = await orchestrator.run("use failing tool", ctx)

    # Orchestrator returns a response, not a crash
    assert isinstance(result, str)
    assert len(result) > 0

    # History contains the assistant's tool-call message
    tool_call_msgs = [m for m in ctx.history if m.get("role") == "assistant" and m.get("tool_calls")]
    assert len(tool_call_msgs) >= 1
    assert tool_call_msgs[0]["tool_calls"][0]["name"] == "failing_tool"

    # History contains the error tool response
    tool_responses = [m for m in ctx.history if m.get("role") == "tool"]
    assert len(tool_responses) >= 1
    assert "Error executing failing_tool" in tool_responses[0]["content"]
    assert "tool broke" in tool_responses[0]["content"]
