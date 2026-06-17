"""会话标题生成。"""
from __future__ import annotations

import json
import logging
import re

from side.base import SideTask, SideTaskContext
from side.tasks._util import _short_error, _strip_control_chars

logger = logging.getLogger(__name__)

MAX_TITLE_LEN = 80

PROMPT = """\
Generate a concise title (3-7 words) that captures the main topic of this conversation.
IMPORTANT: The title MUST be in the same language as the user's messages.
Use sentence case. Return JSON with a single "title" field.

Examples:
{"title": "修复移动端登录按钮"}
{"title": "Add OAuth authentication"}
{"title": "记忆系统重构"}
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
        # 提取用户消息用于回退
        user_msgs = [
            m["content"]
            for m in ctx.session_messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ]
        if not user_msgs and ctx.user_input:
            user_msgs = [ctx.user_input]
        if not user_msgs:
            return None

        # 构建对话上下文：system + 历史消息（跳过 system，保留 user/assistant 交替）
        llm_messages: list[dict[str, str]] = []
        for m in ctx.session_messages:
            if m.get("role") == "system":
                continue
            content = m.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            llm_messages.append({"role": m["role"], "content": content})
        # 追加当前用户输入（如果不在 session_messages 中）
        if ctx.user_input and (not llm_messages or llm_messages[-1].get("content") != ctx.user_input):
            llm_messages.append({"role": "user", "content": ctx.user_input})
        if not llm_messages:
            return _fallback_title(user_msgs)

        try:
            response = await ctx.llm_client.chat(
                messages=[{"role": "system", "content": PROMPT}] + llm_messages,
                model=ctx.side_model,
            )
            data = _extract_json_object(response.content)
            if data and isinstance(data, dict):
                title = _sanitize_title(data.get("title"))
                if title:
                    return title
            # 解析失败或 title 无效 → 回退
            return _fallback_title(user_msgs)
        except Exception as e:
            logger.warning("SessionTitleTask: %s", _short_error(e))
            return _fallback_title(user_msgs)
