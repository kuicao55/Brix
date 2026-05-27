"""工具调用结果摘要。"""
from __future__ import annotations

import json
import logging

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)

PROMPT = """\
Write a short summary label (under 30 chars) describing what these tool calls accomplished.
Think git-commit-subject, not sentence. Past tense. Drop articles.

Examples:
- Searched in auth/
- Fixed NPE in UserService
- Read config.json"""


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
            input_str = json.dumps(dict(tool_input), ensure_ascii=False)[:300]
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
            return response.content.strip() if response.content else None
        except Exception:
            logger.warning("ToolSummaryTask 执行失败", exc_info=True)
            return None
