"""LangGraph-based orchestrator engine."""

from __future__ import annotations

import time
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from orchestrator.engine import OrchestratorContext


class _GraphState(TypedDict, total=False):
    """Internal state carried through the LangGraph nodes."""

    context: OrchestratorContext
    iterations: int
    max_iterations: int
    response: str
    last_llm_response: Any  # LLMResponse or None
    done: bool


class LangGraphOrchestrator:
    """Orchestrator that uses LangGraph's StateGraph.

    State flow:
        plan  -> respond   (no tool calls)
        plan  -> execute   (tool calls present)
        execute -> review
        review -> plan     (re-plan after tool results)
        respond -> END
    """

    def __init__(self, max_iterations: int = 5) -> None:
        self.max_iterations = max_iterations
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        """Construct and compile the LangGraph StateGraph."""
        graph = StateGraph(_GraphState)

        graph.add_node("plan", self._plan_node)
        graph.add_node("execute", self._execute_node)
        graph.add_node("review", self._review_node)
        graph.add_node("respond", self._respond_node)

        graph.set_entry_point("plan")

        # After plan: if done (direct response) -> respond, else -> execute
        graph.add_conditional_edges(
            "plan",
            self._after_plan,
            {True: "respond", False: "execute"},
        )

        graph.add_edge("execute", "review")

        # After review: if done (max iterations or direct response from review) -> respond, else -> plan
        graph.add_conditional_edges(
            "review",
            self._after_review,
            {True: "respond", False: "plan"},
        )

        graph.add_edge("respond", END)

        return graph.compile()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, user_input: str, context: OrchestratorContext) -> str:
        """Main orchestrator entry point. Returns the final assistant text."""
        # resume 时去重：避免重复添加已持久化的 user 消息
        if not context.history or context.history[-1].get("role") != "user" or context.history[-1].get("content") != user_input:
            context.history.append({"role": "user", "content": user_input})

        initial_state: _GraphState = {
            "context": context,
            "iterations": 0,
            "max_iterations": self.max_iterations,
            "response": "",
            "last_llm_response": None,
            "done": False,
        }

        final_state = await self._graph.ainvoke(initial_state)
        return final_state["response"]

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def _plan_node(self, state: _GraphState) -> dict:
        """Call the LLM with current history."""
        context: OrchestratorContext = state["context"]
        iterations: int = state.get("iterations", 0)

        try:
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

            if context.hooks:
                tc_names = [tc.name for tc in response.tool_calls]
                step_data = dict(
                    iter=iterations + 1,
                    tools=tc_names,
                    ms=elapsed,
                    msg_count=len(context.history),
                    prompt=[{"role": m.get("role"), "content": m.get("content", "")}
                            for m in context.history],
                )
                if response.content:
                    step_data["response"] = response.content
                context.hooks.fire("orch_plan", **step_data)
        except Exception as e:
            error_msg = f"Error during planning: {e}"
            return {
                "iterations": iterations,
                "response": error_msg,
                "done": True,
                "last_llm_response": None,
            }

        if not response.tool_calls:
            # Direct response, no tools needed
            context.history.append(
                {"role": "assistant", "content": response.content}
            )
            return {
                "iterations": iterations,
                "response": response.content,
                "done": True,
                "last_llm_response": response,
            }

        # Tool calls present -- need to execute
        return {
            "iterations": iterations,
            "last_llm_response": response,
            "done": False,
        }

    async def _execute_node(self, state: _GraphState) -> dict:
        """Run tool calls via the tool_runner and append results to history."""
        context: OrchestratorContext = state["context"]
        response = state["last_llm_response"]

        tool_calls = []
        for tc in response.tool_calls:
            args = tc.arguments
            if not isinstance(args, dict):
                args = {"raw": args}
            tool_calls.append({
                "id": tc.id or "call_{}".format(uuid.uuid4().hex[:12]),
                "name": tc.name,
                "arguments": args,
            })
        context.history.append({
            "role": "assistant",
            "content": response.content,
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            t0 = time.monotonic()
            try:
                result = await context.tool_runner.run(tc["name"], tc["arguments"])
            except Exception as e:
                result = f"Error executing {tc['name']}: {e}"
            elapsed = int((time.monotonic() - t0) * 1000)

            if context.hooks:
                context.hooks.fire(
                    "tool_exec",
                    name=tc["name"],
                    args=tc["arguments"],
                    result=str(result)[:100],
                    ms=elapsed,
                )

            context.history.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tc["name"],
                "content": str(result),
            })

        return {}

    async def _review_node(self, state: _GraphState) -> dict:
        """Review tool results. Decide whether to re-plan or respond."""
        new_iterations = state.get("iterations", 0) + 1
        max_iter = state.get("max_iterations", self.max_iterations)

        if new_iterations >= max_iter:
            # Max iterations reached — respond with fallback
            context: OrchestratorContext = state["context"]
            fallback = "I was unable to complete the request within the allowed steps."
            context.history.append({"role": "assistant", "content": fallback})
            return {
                "iterations": new_iterations,
                "response": fallback,
                "done": True,
            }

        # Continue to re-plan
        return {
            "iterations": new_iterations,
            "done": False,
        }

    async def _respond_node(self, state: _GraphState) -> dict:
        """Final response node. Just returns the accumulated response."""
        # Response is already set by plan_node or the max_iterations guard.
        return {}

    # ------------------------------------------------------------------
    # Conditional edge functions
    # ------------------------------------------------------------------

    @staticmethod
    def _after_plan(state: _GraphState) -> bool:
        """Return True if we should go to respond (done), False for execute."""
        return state.get("done", False)

    @staticmethod
    def _after_review(state: _GraphState) -> bool:
        """Return True if we should go to respond (done), False to re-plan."""
        return state.get("done", False)

    async def run_stream(self, user_input, context):
        """Streaming orchestrator loop. Yields event dicts to the caller."""
        # resume 时去重：避免重复添加已持久化的 user 消息
        if not context.history or context.history[-1].get("role") != "user" or context.history[-1].get("content") != user_input:
            context.history.append({"role": "user", "content": user_input})

        for iteration in range(1, self.max_iterations + 1):
            tool_schemas = []
            if context.tool_runner and hasattr(context.tool_runner, "get_tool_schemas"):
                tool_schemas = context.tool_runner.get_tool_schemas()

            content_parts = []
            tool_calls = []

            try:
                async for event in context.llm_client.chat_stream(
                    messages=context.history,
                    model=context.model,
                    tools=tool_schemas if tool_schemas else None,
                ):
                    yield event
                    if event.get("type") == "text_delta":
                        content_parts.append(event.get("text", ""))
                    elif event.get("type") == "tool_call":
                        raw_args = event.get("input", {})
                        if not isinstance(raw_args, dict):
                            raw_args = {"raw": raw_args}
                        tool_calls.append({
                            "id": event.get("id") or "call_{}".format(uuid.uuid4().hex[:12]),
                            "name": event.get("name", ""),
                            "arguments": raw_args,
                        })
            except Exception as e:
                yield {"type": "text_delta", "text": "Error during planning: {}".format(e)}
                return

            content = "".join(content_parts)

            if not tool_calls:
                context.history.append({"role": "assistant", "content": content})
                return

            # Tool calls present — record assistant message and execute tools
            context.history.append({
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                t0 = time.monotonic()
                is_error = False
                try:
                    result = await context.tool_runner.run(tc["name"], tc["arguments"])
                except Exception as e:
                    result = "Error executing {}: {}".format(tc["name"], e)
                    is_error = True
                elapsed = int((time.monotonic() - t0) * 1000)

                if context.hooks:
                    context.hooks.fire(
                        "tool_exec",
                        name=tc["name"],
                        args=tc["arguments"],
                        result=str(result)[:100],
                        ms=elapsed,
                    )

                yield {
                    "type": "tool_result",
                    "id": tc["id"],
                    "name": tc["name"],
                    "result": str(result),
                    "ms": elapsed,
                    "is_error": is_error,
                }

                context.history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "content": str(result),
                })

        # Exhausted iterations — yield a fallback
        fallback = "I was unable to complete the request within the allowed steps."
        context.history.append({"role": "assistant", "content": fallback})
        yield {"type": "text_delta", "text": fallback}
