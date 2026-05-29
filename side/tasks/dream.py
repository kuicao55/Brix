"""Dream 蒸馏 Side Task。"""
from __future__ import annotations

import logging
from typing import Any

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)


class DreamTask(SideTask):
    """后台 Dream 蒸馏任务。"""

    @property
    def name(self) -> str:
        return "dream"

    async def execute(self, ctx: SideTaskContext) -> None:
        """检查门槛并执行 Dream 蒸馏。"""
        dream = getattr(ctx.memory, "dream", None)
        if dream is None:
            return

        if not dream.should_dream():
            return

        try:
            await dream.run(ctx.llm_client, ctx.side_model)
        except Exception:
            logger.warning("Dream 蒸馏执行失败", exc_info=True)
