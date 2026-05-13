from __future__ import annotations

import copy
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from infra.llm_client import LLMResponse, ToolCall


class AnthropicCompatProvider:
    """Anthropic compatible protocol adapter with long-lived HTTP client."""

    # Beta header for interleaved thinking support
    _THINKING_BETA = "interleaved-thinking-2025-05-14"

    def __init__(self, base_url: str, api_key: str, enable_thinking: bool = True):
        self._client = AsyncAnthropic(base_url=base_url, api_key=api_key)
        self._enable_thinking = enable_thinking

    async def close(self):
        await self._client.close()

    async def chat(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None,
    ) -> LLMResponse:
        # Convert OpenAI-format messages to Anthropic format
        system_msg = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                anthropic_messages.append(self._convert_message(msg))

        kwargs = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": 8192,
        }
        if system_msg:
            kwargs["system"] = system_msg
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        # 启用 thinking（extended thinking）
        extra_headers = {}
        if self._enable_thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 10000}
            extra_headers["anthropic-beta"] = self._THINKING_BETA

        if extra_headers:
            kwargs["extra_headers"] = extra_headers

        response = await self._client.messages.create(**kwargs)

        content = ""
        reasoning_content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "thinking":
                reasoning_content += block.thinking
            elif block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input,
                ))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "stop",
            reasoning_content=reasoning_content,
        )

    async def chat_stream(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream chat completions using Anthropic's streaming API.

        Yields:
            {"type": "text_delta", "text": "..."} for text chunks
            {"type": "thinking_delta", "text": "..."} for thinking chunks
            {"type": "tool_call", "id": ..., "name": ..., "input": ...} at end
        """
        system_msg = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                anthropic_messages.append(self._convert_message(msg))

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": 8192,
        }
        if system_msg:
            kwargs["system"] = system_msg
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        # 启用 thinking（extended thinking）
        extra_headers = {}
        if self._enable_thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 10000}
            extra_headers["anthropic-beta"] = self._THINKING_BETA

        if extra_headers:
            kwargs["extra_headers"] = extra_headers

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield {"type": "text_delta", "text": event.delta.text}
                    elif event.delta.type == "thinking_delta":
                        yield {"type": "thinking_delta", "text": event.delta.thinking}

            # Get the final assembled message for tool_use blocks
            final_message = await stream.get_final_message()
            for block in final_message.content:
                if block.type == "tool_use":
                    yield {
                        "type": "tool_call",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert OpenAI function calling format to Anthropic tool format."""
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                })
        return anthropic_tools

    def _convert_message(self, msg: dict) -> dict:
        """Convert an OpenAI-format message to Anthropic format."""
        role = msg.get("role", "")

        # Assistant with tool_calls -> content blocks with tool_use
        if role == "assistant" and msg.get("tool_calls"):
            content = []
            if msg.get("content"):
                content.append({"type": "text", "text": msg["content"]})
            for tc in msg["tool_calls"]:
                content.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "input": tc.get("arguments", {}),
                })
            result: dict[str, Any] = {"role": "assistant", "content": content}
            return result

        # Tool result -> user message with tool_result content block
        if role == "tool":
            return {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                }],
            }

        # 仅保留 Anthropic API 认识的字段，过滤 tool_name 等非标准字段
        cleaned = {k: v for k, v in msg.items() if k in ("role", "content", "name")}
        return cleaned if cleaned else copy.deepcopy(msg)
