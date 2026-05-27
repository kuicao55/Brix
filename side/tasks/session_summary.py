"""离开后回来的会话摘要。"""
from __future__ import annotations

import logging

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)

PROMPT_ZH = """\
用户离开后回来了。用中文写 1-3 句话。
先说明用户在做什么（高层目标，不是实现细节），然后说明下一步具体操作。
不要写状态报告或提交总结。"""


class SessionSummaryTask(SideTask):
    @property
    def name(self) -> str:
        return "session_summary"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        if not ctx.session_messages:
            return None
        recent = ctx.session_messages[-15:]
        conversation = "\n".join(
            f"{'用户' if m.get('role') == 'user' else '助手'}: "
            f"{str(m.get('content', ''))[:200]}"
            for m in recent
            if isinstance(m.get("content"), str)
        )
        try:
            response = await ctx.llm_client.chat(
                messages=[
                    {"role": "system", "content": PROMPT_ZH},
                    {"role": "user", "content": f"最近的对话:\n{conversation}"},
                ],
                model=ctx.side_model,
            )
            return response.content if response.content else None
        except Exception:
            logger.warning("SessionSummaryTask 执行失败", exc_info=True)
            return None
