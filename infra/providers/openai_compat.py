from __future__ import annotations

import json

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
