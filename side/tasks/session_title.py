"""会话标题生成。"""
from __future__ import annotations

import json
import logging
import re

from side.base import SideTask, SideTaskContext
from side.tasks._util import _strip_control_chars

logger = logging.getLogger(__name__)

MAX_TITLE_LEN = 80

PROMPT = """\
Generate a concise title (3-7 words) that captures the main topic of this conversation.
Use sentence case. Return JSON with a single "title" field.

Examples:
{"title": "Fix login button on mobile"}
{"title": "Add OAuth authentication"}
{"title": "Debug failing CI tests"}"""


def _extract_json_object(text: str) -> dict | None:
    """容错提取：从 fenced / plain 文本中解析第一个 JSON 对象。"""
    # 尝试 ```json ... ``` fenced 块
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    # 尝试直接解析整个文本
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # 尝试在文本中找第一个 { ... } 对象
    brace_match = re.search(r"\{.*?\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _sanitize_title(raw: str | None) -> str | None:
    """校验并清理标题：剥离控制字符、折叠换行、截断长度。"""
    if not isinstance(raw, str):
        return None
    cleaned = _strip_control_chars(raw)
    # 折叠换行为空格，去首尾空白
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        return None
    return cleaned[:MAX_TITLE_LEN]


def _fallback_title(user_msgs: list[str]) -> str | None:
    """JSON 解析失败时，用首条用户消息作回退标题。"""
    if not user_msgs:
        return None
    return _sanitize_title(user_msgs[0])


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
            data = _extract_json_object(response.content)
            if data and isinstance(data, dict):
                title = _sanitize_title(data.get("title"))
                if title:
                    return title
            # 解析失败或 title 无效 → 回退
            return _fallback_title(user_msgs)
        except Exception:
            logger.warning("SessionTitleTask 执行失败", exc_info=True)
            return _fallback_title(user_msgs)
