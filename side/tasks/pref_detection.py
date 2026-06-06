"""用户偏好/习惯检测。"""
from __future__ import annotations

import json
import logging
import re

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)

PROMPT = """\
分析以下对话，提取值得长期记住的用户信息。

判断标准：这条信息在未来对话中是否有用？
- 用户明确表达的偏好、习惯、做事方式
- 用户主动告知或纠正的关于自身的重要事实（身份、职业、生活环境等）
- 助手未来应该记住或注意的事情

不要提取：
- 一次性的闲聊、玩笑、情绪表达
- 因信息不对等产生的正常对话中的临时纠正
- 没有长期记忆价值的细节

用整体语境判断，不要逐句模式匹配。

返回 JSON 数组，每项格式：{"preference": "信息描述", "context": "对话中的依据"}
无发现返回空数组：[]"""


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
        # 只保留 user/assistant 消息，过滤 system 等角色
        conversation = "\n".join(
            f"{'用户' if m.get('role') == 'user' else '助手'}: "
            f"{m.get('content', '')[:200]}"
            for m in recent
            if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
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
            # 将检测到的偏好写入短期记忆
            self._write_to_short_term_memory(ctx, preferences)
            return preferences
        except Exception:
            logger.warning("PrefDetectionTask 执行失败", exc_info=True)
            return None

    @staticmethod
    def _write_to_short_term_memory(ctx: SideTaskContext, preferences: list[dict]) -> None:
        """将偏好写入短期记忆（容错：memory 属性不存在时不报错）。"""
        if not preferences:
            return
        try:
            if not (hasattr(ctx, "memory") and ctx.memory is not None):
                return
            if not (hasattr(ctx.memory, "short_term") and ctx.memory.short_term is not None):
                return
            # 从 _side_task_args 获取 session_id，若无则从 memory 获取
            task_args = ctx.config.get("_side_task_args", {})
            session_id = task_args.get("session_id", "")
            if not session_id and hasattr(ctx.memory, "current_session_id"):
                session_id = ctx.memory.current_session_id or ""
            if not session_id:
                session_id = "current"
            for pref in preferences:
                text = pref.get("preference", "")
                if text:
                    ctx.memory.short_term.add_item(
                        content=text,
                        source="pref_detection",
                        session_id=session_id,
                        context=pref.get("context", ""),
                    )
        except Exception:
            logger.warning("PrefDetectionTask 写入短期记忆失败", exc_info=True)
