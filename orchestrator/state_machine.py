"""State-machine based orchestrator engine."""

from __future__ import annotations

import time
import uuid

from orchestrator.engine import OrchestratorContext
from orchestrator.states import OrchestratorState


def _summarize_history(history: list[dict]) -> list[dict]:
    """Return a compact summary of message history for logging."""
    result = []
    for m in history:
        entry: dict = {"role": m.get("role", "?")}
        content = m.get("content")
        if content:
            entry["content"] = content
        if m.get("tool_calls"):
            entry["tool_calls"] = m["tool_calls"]
        if m.get("tool_call_id"):
            entry["tool_call_id"] = m["tool_call_id"]
        if m.get("tool_name"):
            entry["tool_name"] = m["tool_name"]
        result.append(entry)
    return result


class StateMachineOrchestrator:
    """Orchestrator that uses a plan/execute/review loop.

    State flow:
        PLANNING -> RESPONDING  (no tool calls)
        PLANNING -> EXECUTING   (tool calls present)
        EXECUTING -> REVIEWING  (tools have run)
        REVIEWING -> PLANNING   (re-plan after tool results)
        REVIEWING -> RESPONDING (task complete)
    """

    def __init__(self, max_iterations: int = 5) -> None:
        self.max_iterations = max_iterations
        self._current_iter = 0

    async def run(self, user_input: str, context: OrchestratorContext) -> str:
        """Main orchestrator loop. Returns the final assistant text."""
        context.history.append({"role": "user", "content": user_input})

        for self._current_iter in range(1, self.max_iterations + 1):
            try:
                response = await self._plan(context)
            except Exception as e:
                return f"Error during planning: {e}"

            if not response.tool_calls:
                context.history.append(
                    {"role": "assistant", "content": response.content}
                )
                return response.content

            # Tool calls present — execute them
            await self._execute(context, response)

        # Exhausted iterations — return a fallback
        fallback = "I was unable to complete the request within the allowed steps."
        context.history.append({"role": "assistant", "content": fallback})
        return fallback

    async def _plan(self, context: OrchestratorContext) -> object:
        """Call the LLM with current history. Returns LLMResponse."""
        tool_schemas = []
        if context.tool_runner and hasattr(context.tool_runner, "get_tool_schemas"):
            tool_schemas = context.tool_runner.get_tool_schemas()

        t0 = time.monotonic()
        response = await context.llm_client.chat(
            messages=context.history,
            model=context.model,
            tools=tool_schemas if tool_schemas else None,
        )
        elapsed = int((time.monotonic() - t0) * 1000)

        if context.log:
            tc_names = [tc.name for tc in response.tool_calls]
            step_data = dict(
                iter=self._current_iter,
                tools=tc_names,
                ms=elapsed,
                msg_count=len(context.history),
                prompt=_summarize_history(context.history),
            )
            if response.content:
                step_data["response"] = response.content
            context.log.step("orch_plan", **step_data)
        return response

    async def _execute(
        self, context: OrchestratorContext, response: object
    ) -> None:
        """Run tool calls via the tool_runner and append results to history."""
        # Record the assistant's tool-call message, generating synthetic IDs
        # when the provider doesn't populate them (some OpenAI-compatible
        # endpoints, older responses).
        tool_calls = [
            {
                "id": tc.id or f"call_{uuid.uuid4().hex[:12]}",
                "name": tc.name,
                "arguments": tc.arguments,
            }
            for tc in response.tool_calls
        ]
        context.history.append({
            "role": "assistant",
            "content": response.content,
            "tool_calls": tool_calls,
        })

        # Run each tool and append results
        for tc in tool_calls:
            t0 = time.monotonic()
            try:
                result = await context.tool_runner.run(tc["name"], tc["arguments"])
            except Exception as e:
                result = f"Error executing {tc['name']}: {e}"
            elapsed = int((time.monotonic() - t0) * 1000)

            if context.log:
                context.log.step(
                    "tool_exec",
                    name=tc["name"],
                    args=tc["arguments"],
                    result=str(result)[:100],
                    ms=elapsed,
                )

            context.history.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "tool_name": tc["name"],
                "content": str(result),
            })

    def _extract_response(self, context: OrchestratorContext) -> str:
        """Get the last assistant message from history."""
        for msg in reversed(context.history):
            if msg.get("role") == "assistant" and msg.get("content"):
                return msg["content"]
        return ""
