"""长对话上下文压缩。"""
from __future__ import annotations

import logging

from side.base import SideTask, SideTaskContext
from side.tasks._util import _strip_control_chars

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
        # 优先检查 token 触发：如果设置了 max_context，按 token 数判断
        task_args = ctx.config.get("_side_task_args", {})
        max_context = task_args.get("max_context")
        if max_context is not None:
            total_tokens = sum(
                len(str(m.get("content", ""))) // 4
                for m in ctx.session_messages
            )
            if total_tokens >= max_context * 0.8:
                logger.debug(
                    "ContextCompressTask: token 触发 (%d >= %d*0.8=%d)",
                    total_tokens, max_context, int(max_context * 0.8),
                )
            else:
                return None
        else:
            # 回退：按消息数触发
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
            # 归一化：strip 控制字符 + 首尾空白
            result = _strip_control_chars(response.content).strip()
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
