"""历史记忆语义搜索。"""
from __future__ import annotations

import json
import logging
import re

from side.base import SideTask, SideTaskContext
from side.tasks._util import _short_error

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


def _validate_keywords(raw: object, defaults: list[str]) -> list[str]:
    """校验 trigger_keywords 配置项。

    要求为字符串序列，每项非空。自动 lowercase + strip。
    标量、含非字符串元素、全为空串等情况回退到 defaults。
    """
    if not isinstance(raw, list):
        return defaults
    cleaned: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            return defaults
        kw = item.strip().lower()
        if kw:
            cleaned.append(kw)
    return cleaned if cleaned else defaults


def _extract_int_list(text: str) -> list[int]:
    """容错提取：从 LLM 响应中解析 JSON 整数数组。

    策略与 _extract_json_array 相同，但额外过滤非 int 元素。
    """
    raw_list = _extract_json_array(text)
    if raw_list is None:
        return []
    return [i for i in raw_list if isinstance(i, int)]


def _extract_json_array(text: str) -> list | None:
    """容错提取：从 LLM 响应中解析第一个 JSON 数组。"""
    # 1) 直接解析
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # 2) fenced 代码块
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fenced:
        try:
            result = json.loads(fenced.group(1))
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # 3) 逐个扫描方括号片段（支持嵌套括号）
    for i, ch in enumerate(text):
        if ch != "[":
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
            if depth == 0:
                try:
                    result = json.loads(text[i : j + 1])
                    if isinstance(result, list):
                        return result
                except (json.JSONDecodeError, ValueError):
                    pass
                break
    return None


class HistorySearchTask(SideTask):
    @property
    def name(self) -> str:
        return "history_search"

    def should_trigger(self, user_input: str, config: dict | None = None) -> bool:
        raw_keywords = (
            (config or {}).get("side", {}).get("tasks", {})
            .get("history_search", {}).get("trigger_keywords", TRIGGER_KEYWORDS)
        )
        keywords = _validate_keywords(raw_keywords, TRIGGER_KEYWORDS)
        text = user_input.lower()
        return any(kw in text for kw in keywords)

    async def execute(self, ctx: SideTaskContext) -> list[dict] | None:
        if not self.should_trigger(ctx.user_input, ctx.config):
            return None
        if not ctx.memory:
            return None
        try:
            sessions = ctx.memory.list_sessions()
        except Exception as e:
            logger.warning("HistorySearchTask: %s", _short_error(e))
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
            indices = _extract_int_list(response.content or "[]")
            results = []
            for i in indices[:top_k]:
                if 0 <= i < len(candidate_sessions):
                    results.append(candidate_sessions[i])
            return results
        except Exception as e:
            logger.warning("HistorySearchTask: %s", _short_error(e))
            return None
