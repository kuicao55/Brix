"""短期记忆摘要任务。"""
from __future__ import annotations

import logging

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)


class MemorySummaryTask(SideTask):
    """从短期记忆生成近期摘要。"""

    @property
    def name(self) -> str:
        return "memory_summary"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        # 获取短期记忆
        if not ctx.memory or not hasattr(ctx.memory, "short_term"):
            return None

        try:
            recent_items = ctx.memory.short_term.get_recent(limit=10)
        except Exception:
            logger.warning("MemorySummaryTask: 获取短期记忆失败", exc_info=True)
            return None

        if not recent_items:
            return None

        # 格式化摘要
        summary_lines = []
        for item in recent_items:
            if isinstance(item, dict):
                content = item.get("content", "")
                if content and isinstance(content, str):
                    summary_lines.append(f"- {content}")

        if not summary_lines:
            return None

        return "\n".join(summary_lines)
