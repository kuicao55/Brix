from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from infra.llm_client import LLMResponse, ToolCall


class OpenAICompatProvider:
    """OpenAI compatible protocol adapter."""

    async def chat(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None,
        base_url: str,
        api_key: str,
    ) -> LLMResponse:
        client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        try:
            kwargs = {"model": model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = await client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    raw_args = tc.function.arguments
                    if isinstance(raw_args, dict):
                        arguments = raw_args
                    elif isinstance(raw_args, str):
                        try:
                            parsed = json.loads(raw_args)
                            arguments = parsed if isinstance(parsed, dict) else {"raw": raw_args}
                        except (json.JSONDecodeError, TypeError):
                            arguments = {"raw": raw_args}
                    else:
                        arguments = {"raw": raw_args}
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=arguments,
                    ))

            return LLMResponse(
                content=choice.message.content or "",
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason,
            )
        finally:
            await client.close()

    async def chat_stream(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None,
        base_url: str,
        api_key: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream chat completions, yielding event dicts.

        Yields:
            {"type": "text_delta", "text": "..."} for content chunks
            {"type": "tool_call", "id": ..., "name": ..., "arguments": ...} at end
        """
        client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        try:
            kwargs: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            stream = client.chat.completions.create(**kwargs)

            # Accumulate tool call deltas across chunks
            # keyed by tool call index
            tc_buffers: dict[int, dict[str, Any]] = defaultdict(
                lambda: {"id": None, "name": "", "arguments": ""}
            )

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Yield text content
                if delta.content:
                    yield {"type": "text_delta", "text": delta.content}

                # Accumulate tool call deltas
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        buf = tc_buffers[idx]
                        if tc_delta.id:
                            buf["id"] = tc_delta.id
                        if tc_delta.function and tc_delta.function.name:
                            buf["name"] = tc_delta.function.name
                        if tc_delta.function and tc_delta.function.arguments:
                            buf["arguments"] += tc_delta.function.arguments

            # Flush accumulated tool calls
            for idx in sorted(tc_buffers.keys()):
                buf = tc_buffers[idx]
                raw_args = buf["arguments"]
                try:
                    parsed = json.loads(raw_args) if raw_args else {}
                    arguments = parsed if isinstance(parsed, dict) else {"raw": raw_args}
                except (json.JSONDecodeError, TypeError):
                    arguments = {"raw": raw_args}

                yield {
                    "type": "tool_call",
                    "id": buf["id"],
                    "name": buf["name"],
                    "arguments": arguments,
                }
        finally:
            await client.close()
