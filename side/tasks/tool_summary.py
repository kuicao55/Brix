"""工具调用结果摘要。"""
from __future__ import annotations

import json
import logging

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)

MAX_SUMMARY_LEN = 30

PROMPT = """\
Write a short summary label (under 30 chars) describing what these tool calls accomplished.
Think git-commit-subject, not sentence. Past tense. Drop articles.

Examples:
- Searched in auth/
- Fixed NPE in UserService
- Read config.json"""


def _serialize_tool_input(tool_input: object) -> str:
    """安全序列化 tool_input，不假设其类型。"""
    try:
        return json.dumps(tool_input, ensure_ascii=False, default=str)[:300]
    except (TypeError, ValueError):
        return repr(tool_input)[:300]


def _sanitize_summary(raw: str | None) -> str | None:
    """校验并清理摘要：要求字符串、折叠换行、截断长度。"""
    if not isinstance(raw, str):
        return None
    cleaned = " ".join(raw.split()).strip()
    if not cleaned:
        return None
    return cleaned[:MAX_SUMMARY_LEN]


class ToolSummaryTask(SideTask):
    @property
    def name(self) -> str:
        return "tool_summary"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        try:
            task_args = ctx.config.get("_side_task_args", {})
            tool_name = task_args.get("tool_name", "")
            tool_input = task_args.get("tool_input", {})
            tool_result = task_args.get("tool_result", "")
            input_str = _serialize_tool_input(tool_input)
            output_str = str(tool_result)[:300]
            user_prompt = (
                f"Tool: {tool_name}\nInput: {input_str}\n"
                f"Output: {output_str}\n\nLabel:"
            )
            response = await ctx.llm_client.chat(
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=ctx.side_model,
            )
            return _sanitize_summary(response.content)
        except Exception:
            logger.warning("ToolSummaryTask 执行失败", exc_info=True)
            return None
