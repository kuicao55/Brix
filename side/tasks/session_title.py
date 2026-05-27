"""会话标题生成。"""
from __future__ import annotations

import json
import logging

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)

PROMPT = """\
Generate a concise title (3-7 words) that captures the main topic of this conversation.
Use sentence case. Return JSON with a single "title" field.

Examples:
{"title": "Fix login button on mobile"}
{"title": "Add OAuth authentication"}
{"title": "Debug failing CI tests"}"""


class SessionTitleTask(SideTask):
    @property
    def name(self) -> str:
        return "session_title"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        user_msgs = [
            m["content"]
            for m in ctx.session_messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ][:3]
        if not user_msgs:
            return None
        prompt_text = "\n".join(user_msgs)
        try:
            response = await ctx.llm_client.chat(
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": prompt_text},
                ],
                model=ctx.side_model,
            )
            data = json.loads(response.content)
            return data.get("title")
        except Exception:
            logger.warning("SessionTitleTask 执行失败", exc_info=True)
            return None
