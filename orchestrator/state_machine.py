"""State-machine based orchestrator engine."""

from __future__ import annotations

from orchestrator.engine import OrchestratorContext
from orchestrator.states import OrchestratorState


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

    async def run(self, user_input: str, context: OrchestratorContext) -> str:
        """Main orchestrator loop. Returns the final assistant text."""
        context.history.append({"role": "user", "content": user_input})

        for _ in range(self.max_iterations):
            response = await self._plan(context)

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
        return await context.llm_client.chat(
            messages=context.history,
            model=context.model,
        )

    async def _execute(
        self, context: OrchestratorContext, response: object
    ) -> None:
        """Run tool calls via the tool_runner and append results to history."""
        # Record the assistant's tool-call message
        context.history.append({
            "role": "assistant",
            "content": response.content,
            "tool_calls": [
                {"name": tc.name, "arguments": tc.arguments}
                for tc in response.tool_calls
            ],
        })

        # Run tools
        results = await context.tool_runner.run(response.tool_calls)

        # Append tool results to history
        for result in results:
            context.history.append({
                "role": "tool",
                "content": str(result),
            })

    def _extract_response(self, context: OrchestratorContext) -> str:
        """Get the last assistant message from history."""
        for msg in reversed(context.history):
            if msg.get("role") == "assistant" and msg.get("content"):
                return msg["content"]
        return ""
