"""State-machine based orchestrator engine."""

from __future__ import annotations

import json
import time
import uuid

from capability.tools.skill_tool import SKILL_PROMPT_PREFIX
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

    def __init__(self, max_iterations: int = 100) -> None:
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
        fallback = f"I was unable to complete the request within {self.max_iterations} steps."
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

        if context.hooks:
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
            context.hooks.fire("orch_plan", **step_data)
        return response

    async def _execute(
        self, context: OrchestratorContext, response: object
    ) -> None:
        """Run tool calls via the tool_runner and append results to history."""
        # Record the assistant's tool-call message, generating synthetic IDs
        # when the provider doesn't populate them (some OpenAI-compatible
        # endpoints, older responses).
        tool_calls = []
        for tc in response.tool_calls:
            args = tc.arguments
            if not isinstance(args, dict):
                args = {"raw": args}
            tool_calls.append({
                "id": tc.id or "call_{}".format(uuid.uuid4().hex[:12]),
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            })
        assistant_msg: dict = {
            "role": "assistant",
            "content": response.content,
            "tool_calls": tool_calls,
        }
        if hasattr(response, "reasoning_content") and response.reasoning_content:
            assistant_msg["reasoning_content"] = response.reasoning_content
        context.history.append(assistant_msg)

        # Run each tool and append results
        for tc in tool_calls:
            t0 = time.monotonic()
            tc_name = tc["function"]["name"]
            try:
                tc_args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, TypeError):
                tc_args = {"raw": tc["function"]["arguments"]}
            try:
                result = await context.tool_runner.run(tc_name, tc_args)
            except Exception as e:
                result = f"Error executing {tc_name}: {e}"
            elapsed = int((time.monotonic() - t0) * 1000)
            is_error = str(result).startswith("Error")

            if context.hooks:
                context.hooks.fire(
                    "tool_exec",
                    name=tc_name,
                    args=tc_args,
                    result=str(result)[:100],
                    ms=elapsed,
                )

            # Skill 指令：注入为 user message，让 LLM 按指令执行
            result_str = str(result)
            if result_str.startswith(SKILL_PROMPT_PREFIX):
                skill_prompt = result_str[len(SKILL_PROMPT_PREFIX):]
                context.history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc_name,
                    "content": f"Launching skill: {tc_name}",
                })
                context.history.append({
                    "role": "user",
                    "content": skill_prompt,
                })
            else:
                context.history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc_name,
                    "content": result_str,
                })

    async def run_stream(self, user_input, context):
        """Streaming orchestrator loop. Yields event dicts to the caller."""
        context.history.append({"role": "user", "content": user_input})

        for iteration in range(1, self.max_iterations + 1):
            tool_schemas = []
            if context.tool_runner and hasattr(context.tool_runner, "get_tool_schemas"):
                tool_schemas = context.tool_runner.get_tool_schemas()

            content_parts = []
            reasoning_parts = []
            tool_calls = []
            t0 = time.monotonic()

            try:
                async for event in context.llm_client.chat_stream(
                    messages=context.history,
                    model=context.model,
                    tools=tool_schemas if tool_schemas else None,
                ):
                    yield event
                    if event.get("type") == "text_delta":
                        content_parts.append(event.get("text", ""))
                    elif event.get("type") == "thinking_delta":
                        reasoning_parts.append(event.get("text", ""))
                    elif event.get("type") == "tool_call":
                        raw_args = event.get("input", {})
                        if not isinstance(raw_args, dict):
                            raw_args = {"raw": raw_args}
                        # DeepSeek API 要求 tool_calls 用 function wrapper 格式
                        tool_calls.append({
                            "id": event.get("id") or "call_{}".format(uuid.uuid4().hex[:12]),
                            "type": "function",
                            "function": {
                                "name": event.get("name", ""),
                                "arguments": json.dumps(raw_args, ensure_ascii=False),
                            },
                        })
            except Exception as e:
                yield {"type": "text_delta", "text": "Error during planning: {}".format(e)}
                return

            content = "".join(content_parts)
            reasoning_content = "".join(reasoning_parts)

            # Fire orch_plan hook — streaming LLM call completed
            elapsed = int((time.monotonic() - t0) * 1000)
            tc_names = [tc["function"]["name"] for tc in tool_calls]
            if context.hooks:
                context.hooks.fire(
                    "orch_plan",
                    iter=iteration,
                    tools=tc_names,
                    ms=elapsed,
                    msg_count=len(context.history),
                    prompt=_summarize_history(context.history),
                    response=content[:200] if content else "",
                )

            if not tool_calls:
                msg: dict = {"role": "assistant", "content": content}
                if reasoning_content:
                    msg["reasoning_content"] = reasoning_content
                context.history.append(msg)
                return

            # Tool calls present — record assistant message and execute tools
            assistant_msg: dict = {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            }
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            context.history.append(assistant_msg)

            for tc in tool_calls:
                t0 = time.monotonic()
                is_error = False
                tc_name = tc["function"]["name"]
                try:
                    tc_args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    tc_args = {"raw": tc["function"]["arguments"]}
                try:
                    result = await context.tool_runner.run(tc_name, tc_args)
                except Exception as e:
                    result = "Error executing {}: {}".format(tc_name, e)
                elapsed = int((time.monotonic() - t0) * 1000)
                is_error = str(result).startswith("Error")

                if context.hooks:
                    context.hooks.fire(
                        "tool_exec",
                        name=tc_name,
                        args=tc_args,
                        result=str(result)[:100],
                        ms=elapsed,
                    )

                # Skill 指令：注入为 user message，让 LLM 按指令执行
                result_str = str(result)
                if result_str.startswith(SKILL_PROMPT_PREFIX):
                    skill_prompt = result_str[len(SKILL_PROMPT_PREFIX):]
                    yield {
                        "type": "tool_result",
                        "id": tc["id"],
                        "name": tc_name,
                        "result": f"Launching skill: {tc_name}",
                        "ms": elapsed,
                        "is_error": False,
                    }
                    context.history.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tc_name,
                        "content": f"Launching skill: {tc_name}",
                    })
                    context.history.append({
                        "role": "user",
                        "content": skill_prompt,
                    })
                else:
                    yield {
                        "type": "tool_result",
                        "id": tc["id"],
                        "name": tc_name,
                        "result": result_str,
                        "ms": elapsed,
                        "is_error": is_error,
                    }
                    context.history.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tc_name,
                        "content": result_str,
                    })

        # Exhausted iterations — yield a fallback
        fallback = f"I was unable to complete the request within {self.max_iterations} steps."
        context.history.append({"role": "assistant", "content": fallback})
        yield {"type": "text_delta", "text": fallback}

    def _extract_response(self, context: OrchestratorContext) -> str:
        """Get the last assistant message from history."""
        for msg in reversed(context.history):
            if msg.get("role") == "assistant" and msg.get("content"):
                return msg["content"]
        return ""
