"""OpenAI compatible protocol adapter with long-lived HTTP client."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from infra.llm_client import LLMResponse, ToolCall


def _parse_think_tags(content: str) -> tuple[str, str]:
    """从 content 中提取 <think> 标签内的 reasoning 内容。

    Returns:
        (reasoning, clean_content) — reasoning 可能为空
    """
    match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
    if match:
        reasoning = match.group(1).strip()
        clean = content[:match.start()] + content[match.end():]
        return reasoning, clean.strip()
    return "", content


def _extract_reasoning_details(message_or_delta: Any) -> str:
    """从 message 或 delta 对象中提取 reasoning_details 文本。

    MiniMax 的 reasoning_details 格式:
    [{"type": "reasoning.text", "id": "...", "text": "..."}]
    """
    # 先检查直接属性
    details = getattr(message_or_delta, "reasoning_details", None)
    if details is None:
        # 再检查 model_extra
        extra = getattr(message_or_delta, "model_extra", None) or {}
        details = extra.get("reasoning_details", None)
    if not details:
        return ""

    parts = []
    for item in details:
        if isinstance(item, dict):
            text = item.get("text", "")
            if text:
                parts.append(text)
        elif hasattr(item, "text"):
            parts.append(item.text)
    return "".join(parts)


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
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "extra_body": {"reasoning_split": True},
        }
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

        content = choice.message.content or ""

        # 提取 reasoning：先尝试 reasoning_details，再尝试 <think> 标签
        reasoning = _extract_reasoning_details(choice.message)
        if not reasoning and "<think>" in content:
            reasoning, content = _parse_think_tags(content)

        # DeepSeek 兼容：model_extra 中的 reasoning 字段
        if not reasoning:
            extra = getattr(choice.message, "model_extra", None) or {}
            reasoning = extra.get("reasoning", "") or ""

        return LLMResponse(
            content=content,
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
            {"type": "thinking_delta", "text": "..."} for thinking/reasoning chunks
            {"type": "tool_call", "id": ..., "name": ..., "input": ...} at end
        """
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "extra_body": {"reasoning_split": True},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**kwargs)

        # Accumulate tool call deltas across chunks, keyed by tool call index
        tc_buffers: dict[int, dict[str, Any]] = defaultdict(
            lambda: {"id": None, "name": "", "input": ""}
        )
        # 收集 content 用于 <think> 标签回退解析
        content_parts: list[str] = []
        has_reasoning_details = False

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # 1. reasoning_details（MiniMax Interleaved Thinking）
            reasoning_text = _extract_reasoning_details(delta)
            if reasoning_text:
                has_reasoning_details = True
                yield {"type": "thinking_delta", "text": reasoning_text}

            # 2. DeepSeek reasoning 字段
            if not reasoning_text:
                extra = getattr(delta, "model_extra", None) or {}
                ds_reasoning = extra.get("reasoning", "")
                if ds_reasoning:
                    yield {"type": "thinking_delta", "text": ds_reasoning}

            # 3. 文本内容
            if delta.content:
                yield {"type": "text_delta", "text": delta.content}
                content_parts.append(delta.content)

            # 4. 累积 tool call deltas
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

        # 回退：如果没收到 reasoning_details 但 content 中有 <think> 标签
        if not has_reasoning_details and content_parts:
            full_content = "".join(content_parts)
            if "<think>" in full_content:
                reasoning, _ = _parse_think_tags(full_content)
                if reasoning:
                    yield {"type": "thinking_delta", "text": reasoning}

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
