from __future__ import annotations

import copy

from anthropic import AsyncAnthropic

from infra.llm_client import LLMResponse, ToolCall


class AnthropicCompatProvider:
    """Anthropic compatible protocol adapter."""

    async def chat(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None,
        base_url: str,
        api_key: str,
    ) -> LLMResponse:
        client = AsyncAnthropic(base_url=base_url, api_key=api_key)
        try:
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
                "max_tokens": 4096,
            }
            if system_msg:
                kwargs["system"] = system_msg
            if tools:
                kwargs["tools"] = self._convert_tools(tools)

            response = await client.messages.create(**kwargs)

            content = ""
            tool_calls = []
            for block in response.content:
                if block.type == "text":
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
            )
        finally:
            await client.close()

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
            return {"role": "assistant", "content": content}

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

        return copy.deepcopy(msg)
