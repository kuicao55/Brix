from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from infra.llm_client import LLMResponse, ToolCall


class OpenAICompatProvider:
    """OpenAI compatible protocol adapter with long-lived HTTP client."""

    def __init__(self, base_url: str, api_key: str):
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def close(self):
        await self._client.close()

    async def chat(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None,
    ) -> LLMResponse:
        kwargs = {"model": model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
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

        # DeepSeek thinking 模式：API 返回 reasoning 字段，传回时需用 reasoning_content
        reasoning = ""
        if hasattr(choice.message, "model_extra") and choice.message.model_extra:
            reasoning = choice.message.model_extra.get("reasoning", "") or ""

        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            reasoning_content=reasoning,
        )

    async def chat_stream(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream chat completions, yielding event dicts.

        Yields:
            {"type": "text_delta", "text": "..."} for content chunks
            {"type": "tool_call", "id": ..., "name": ..., "input": ...} at end
        """
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**kwargs)

        # Accumulate tool call deltas across chunks
        # keyed by tool call index
        tc_buffers: dict[int, dict[str, Any]] = defaultdict(
            lambda: {"id": None, "name": "", "input": ""}
        )

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # DeepSeek thinking: reasoning 字段（传回时需用 reasoning_content）
            extra = getattr(delta, "model_extra", None) or {}
            reasoning_text = extra.get("reasoning", "")
            if reasoning_text:
                yield {"type": "thinking_delta", "text": reasoning_text}

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
                        buf["input"] += tc_delta.function.arguments

        # Flush accumulated tool calls
        for idx in sorted(tc_buffers.keys()):
            buf = tc_buffers[idx]
            raw_args = buf["input"]
            try:
                parsed = json.loads(raw_args) if raw_args else {}
                arguments = parsed if isinstance(parsed, dict) else {"raw": raw_args}
            except (json.JSONDecodeError, TypeError):
                arguments = {"raw": raw_args}

            yield {
                "type": "tool_call",
                "id": buf["id"],
                "name": buf["name"],
                "input": arguments,
            }
