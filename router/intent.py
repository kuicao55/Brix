"""Intent classification using LLM."""

from __future__ import annotations

import re
import time
from typing import Any

# Intent 标签定义
VALID_INTENTS = {"chat", "deep_chat", "knowledge", "code", "tool_use", "image", "video"}

INTENT_SYSTEM_PROMPT = """\
You are an intent classifier. Given the user message, classify it into exactly one category:

- chat: casual conversation, greetings, small talk, simple questions
- deep_chat: deep discussion, debate, philosophical questions, complex analysis, comparison requiring reasoning
- knowledge: factual questions, explanations, how-to, science, history, math
- code: coding, debugging, code review, programming questions, technical implementation
- tool_use: requests to use tools like weather, calculator, file operations, search
- image: requests to generate, create, or draw images, pictures, illustrations
- video: requests to generate or create videos

Respond with ONLY one of: chat, deep_chat, knowledge, code, tool_use, image, video"""

# 启发式关键词（LLM 失败时的 fallback）
_TOOL_KEYWORDS = ["天气", "weather", "calculate", "计算", "read file", "search", "搜索",
                   "查找文件", "look up", "打开", "读取"]
_CODE_KEYWORDS = ["代码", "code", "debug", "bug", "编程", "函数", "function", "class",
                   "api", "sql", "git", "npm", "pip", "编译", "报错", "error", "import",
                   "typescript", "python", "java", "rust", "html", "css"]
_KNOWLEDGE_KEYWORDS = ["什么是", "为什么", "怎么", "如何", "解释", "原理", "what is",
                        "why", "how does", "explain", "区别", "difference", "历史",
                        "science", "数学", "math"]
_DEEP_KEYWORDS = ["分析", "analyze", "比较", "compare", "思考", "think", "评价",
                   "evaluate", "观点", "opinion", "辩论", "debate", "哲学", "深度"]
_IMAGE_KEYWORDS = ["画", "绘制", "生成图", "图片", "image", "draw", "picture",
                    "illustration", "生成一张", "帮我画"]
_VIDEO_KEYWORDS = ["视频", "video", "生成视频", "动画", "animation"]


def _summarize_msgs(messages: list[dict]) -> list[dict]:
    """Return a compact summary of messages for logging."""
    result = []
    for m in messages:
        entry: dict = {"role": m.get("role", "?")}
        content = m.get("content", "")
        if isinstance(content, str):
            entry["content"] = content
        elif isinstance(content, list):
            # Anthropic-style content blocks
            entry["content"] = [
                {k: v for k, v in block.items() if k != "input"}
                if block.get("type") == "tool_use" else block
                for block in content
            ]
        result.append(entry)
    return result


def classify_intent_heuristic(user_input: str) -> str:
    """纯规则 intent 分类（无需 LLM）。"""
    text = user_input.lower()

    if any(kw in text for kw in _IMAGE_KEYWORDS):
        return "image"
    if any(kw in text for kw in _VIDEO_KEYWORDS):
        return "video"
    if any(kw in text for kw in _TOOL_KEYWORDS):
        return "tool_use"
    if any(kw in text for kw in _CODE_KEYWORDS):
        return "code"
    if any(kw in text for kw in _KNOWLEDGE_KEYWORDS):
        return "knowledge"
    if any(kw in text for kw in _DEEP_KEYWORDS):
        return "deep_chat"

    return "chat"


async def classify_intent(
    user_input: str,
    history: list[dict],
    llm_client: Any,
    model: str,
    hooks: Any = None,
) -> str:
    """Classify user intent using LLM, with heuristic fallback."""
    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_input},
    ]

    t0 = time.monotonic()

    try:
        response = await llm_client.chat(messages=messages, model=model)
        raw_content = response.content or ""
        first_token = re.split(r"[\s\n]+", raw_content.strip().lower())[0] if raw_content.strip() else ""
        if first_token in VALID_INTENTS:
            elapsed = int((time.monotonic() - t0) * 1000)
            if hooks:
                hooks.fire("intent", result=first_token, via="llm",
                           model=model, response=raw_content.strip(),
                           ms=elapsed, prompt_msgs=len(messages),
                           user_input=user_input,
                           prompt=_summarize_msgs(messages))
            return first_token
    except Exception:
        pass

    # Heuristic fallback
    result = classify_intent_heuristic(user_input)

    elapsed = int((time.monotonic() - t0) * 1000)
    if hooks:
        hooks.fire("intent", result=result, via="heuristic",
                   model=model,
                   ms=elapsed, prompt_msgs=len(messages),
                   user_input=user_input,
                   prompt=_summarize_msgs(messages))
    return result
