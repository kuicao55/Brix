"""长对话上下文压缩。"""
from __future__ import annotations

import logging

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)

# 输出硬上限（字符数）
_MAX_OUTPUT_CHARS = 2000

PROMPT = """\
将以下对话历史压缩为简明摘要，保留：
1. 关键决策和结论
2. 未完成的任务
3. 重要的上下文信息

丢弃：
- 重复的内容
- 已完成的中间步骤
- 礼貌性对话

输出 3-5 句话的摘要。"""


class ContextCompressTask(SideTask):
    @property
    def name(self) -> str:
        return "context_compress"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        threshold = ctx.config.get("side", {}).get("tasks", {}).get(
            "context_compress", {}
        ).get("message_threshold", 50)
        if len(ctx.session_messages) < threshold:
            return None
        half = len(ctx.session_messages) // 2
        old_messages = ctx.session_messages[:half]
        conversation = "\n".join(
            f"{'用户' if m.get('role') == 'user' else '助手'}: "
            f"{str(m.get('content', ''))[:300]}"
            for m in old_messages
            if isinstance(m.get("content"), str)
        )
        try:
            response = await ctx.llm_client.chat(
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": conversation},
                ],
                model=ctx.side_model,
            )
            if not response.content:
                return None
            # 归一化：strip 首尾空白
            result = response.content.strip()
            if not result:
                return None
            # 硬输出预算：超过上限时截断
            if len(result) > _MAX_OUTPUT_CHARS:
                logger.warning(
                    "ContextCompressTask 输出超限 (%d > %d)，截断",
                    len(result),
                    _MAX_OUTPUT_CHARS,
                )
                result = result[:_MAX_OUTPUT_CHARS]
            return result
        except Exception:
            logger.warning("ContextCompressTask 执行失败", exc_info=True)
            return None
