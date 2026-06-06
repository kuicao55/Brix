"""会话退出摘要 — 生成事件摘要并写入短期记忆。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from side.base import SideTask, SideTaskContext
from side.tasks._util import _strip_control_chars

logger = logging.getLogger(__name__)

PROMPT_ZH = """\
请用中文为以下对话历史生成一个简洁的事件摘要（3-5 句话）。
摘要应包含：
1. 用户的主要目标或任务
2. 关键决策或进展
3. 未完成的工作或下一步
不要写状态报告或提交总结。"""


class SessionSummaryTask(SideTask):
    @property
    def name(self) -> str:
        return "session_summary"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        """生成会话事件摘要并写入短期记忆。

        流程：
        1. 检查消息是否为空
        2. 幂等性检查：session 已有 type=event 的摘要时跳过
        3. 通过 LLM 生成摘要
        4. 写入短期记忆（type=event, source=side_summary）
        """
        if not ctx.session_messages:
            return None

        # 获取 session_id — 无 session_id 时无法关联摘要，直接返回
        session_id = getattr(ctx.memory, "current_session_id", None) if ctx.memory else None
        if not session_id:
            return None

        # 幂等性检查：session 已有 type=event 的 item 时跳过
        if session_id and ctx.memory and hasattr(ctx.memory, "short_term") and ctx.memory.short_term:
            existing = ctx.memory.short_term.get_by_session(session_id)
            if any(i.get("type") == "event" for i in existing):
                logger.debug(
                    "SessionSummaryTask: session %s 已有 event 摘要，跳过",
                    str(session_id)[:8],
                )
                return None

        # 生成摘要
        recent = ctx.session_messages[-20:]
        conversation = "\n".join(
            f"{'用户' if m.get('role') == 'user' else '助手'}: "
            f"{str(m.get('content', ''))[:300]}"
            for m in recent
            if isinstance(m.get("content"), str)
        )
        try:
            response = await ctx.llm_client.chat(
                messages=[
                    {"role": "system", "content": PROMPT_ZH},
                    {"role": "user", "content": f"对话历史:\n{conversation}"},
                ],
                model=ctx.side_model,
            )
            summary = _strip_control_chars(response.content).strip() if response.content else None
        except Exception:
            logger.warning("SessionSummaryTask 执行失败", exc_info=True)
            return None

        if not summary:
            return None

        # 写入短期记忆
        if session_id and ctx.memory and hasattr(ctx.memory, "short_term") and ctx.memory.short_term:
            date = self._get_session_date(ctx, session_id)
            ctx.memory.short_term.add_item(
                content=summary,
                source="side_summary",
                type="event",
                date=date,
                session_id=session_id,
            )
            logger.info(
                "SessionSummaryTask: 已写入 session %s 的事件摘要",
                str(session_id)[:8],
            )

        return summary

    @staticmethod
    def _get_session_date(ctx: SideTaskContext, session_id: str) -> str:
        """获取 session 开始日期，格式 YYYY-MM-DD。

        从 session 索引的 created 字段提取日期；
        索引不可用时回退到今天（UTC）。
        """
        try:
            sessions = ctx.memory.list_sessions()
            for s in sessions:
                if s.get("id") == session_id:
                    created = s.get("created", "")
                    if created and len(created) >= 10:
                        return created[:10]  # "YYYY-MM-DD"
        except Exception:
            logger.debug("SessionSummaryTask: 获取 session 日期失败", exc_info=True)
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
