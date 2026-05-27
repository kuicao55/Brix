"""用户偏好/习惯检测。"""
from __future__ import annotations

import json
import logging
import re

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)

PROMPT = """\
分析以下对话，判断用户是否表达了偏好、纠正或习惯性要求。

寻找：
- 纠正："不要这样做"、"应该用..."、"下次记得..."
- 偏好："我喜欢..."、"我希望..."、"请总是..."
- 流程偏好："先...再..."、"帮我记住..."

忽略：
- 一次性的普通对话
- 已经在执行的操作

如果有发现，返回 JSON 数组，每项格式：
{"preference": "偏好描述", "context": "对话中的依据"}

如果没有发现，返回空数组：[]"""


def _extract_json_array(text: str) -> list | None:
    """容错提取：从 LLM 响应中解析第一个 JSON 数组。

    策略：
    1. 尝试直接 json.loads 整段文本
    2. 尝试 ```json ... ``` fenced 代码块
    3. 逐个扫描 [...] 片段，接受第一个可解析为 list 的
    """
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


class PrefDetectionTask(SideTask):
    @property
    def name(self) -> str:
        return "pref_detection"

    async def execute(self, ctx: SideTaskContext) -> list[dict] | None:
        recent = ctx.session_messages[-10:]
        if len(recent) < 3:
            return None
        conversation = "\n".join(
            f"{'用户' if m.get('role') == 'user' else '助手'}: "
            f"{m.get('content', '')[:200]}"
            for m in recent
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
            content = response.content or "[]"
            preferences = _extract_json_array(content)
            if preferences is None:
                preferences = []
            return preferences
        except Exception:
            logger.warning("PrefDetectionTask 执行失败", exc_info=True)
            return None
