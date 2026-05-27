"""历史记忆语义搜索。"""
from __future__ import annotations

import json
import logging

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)

TRIGGER_KEYWORDS = [
    "之前", "上次", "记得", "曾经", "以前", "那时候",
    "previously", "last time", "remember", "before",
]

PROMPT = """\
你是一个会话搜索助手。给定用户查询和一组候选历史会话，按相关性排序。

优先级：
1. 标题直接匹配
2. 内容语义匹配
3. 关键词部分匹配

返回 JSON 数组，包含相关会话的索引号（从 0 开始），按相关性降序排列。
如果没有相关会话，返回空数组：[]"""


class HistorySearchTask(SideTask):
    @property
    def name(self) -> str:
        return "history_search"

    def should_trigger(self, user_input: str, config: dict | None = None) -> bool:
        keywords = (
            (config or {}).get("side", {}).get("tasks", {})
            .get("history_search", {}).get("trigger_keywords", TRIGGER_KEYWORDS)
        )
        text = user_input.lower()
        return any(kw in text for kw in keywords)

    async def execute(self, ctx: SideTaskContext) -> list[dict] | None:
        if not self.should_trigger(ctx.user_input, ctx.config):
            return None
        if not ctx.memory:
            return None
        try:
            sessions = ctx.memory.list_sessions()
        except Exception:
            logger.warning("HistorySearchTask: 获取会话列表失败", exc_info=True)
            return None
        if not sessions:
            return None
        top_k = ctx.config.get("side", {}).get("tasks", {}).get(
            "history_search", {}
        ).get("top_k", 3)
        candidate_sessions = sessions[-20:]
        candidates = []
        for s in candidate_sessions:
            summary = s.get("summary", s.get("title", ""))
            candidates.append(
                f"标题: {s.get('title', '无标题')}\n摘要: {summary[:200]}"
            )
        candidate_text = "\n---\n".join(candidates)
        user_prompt = f"用户查询: {ctx.user_input}\n\n候选会话:\n{candidate_text}"
        try:
            response = await ctx.llm_client.chat(
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=ctx.side_model,
            )
            indices = json.loads(response.content or "[]")
            results = []
            for i in indices[:top_k]:
                if 0 <= i < len(candidate_sessions):
                    results.append(candidate_sessions[i])
            return results
        except Exception:
            logger.warning("HistorySearchTask 执行失败", exc_info=True)
            return None
