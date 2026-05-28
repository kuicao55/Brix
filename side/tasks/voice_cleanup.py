"""语音输入文本清理。"""
from __future__ import annotations

import logging

from side.base import SideTask, SideTaskContext
from side.tasks._util import _strip_control_chars

logger = logging.getLogger(__name__)

PROMPT = """\
清理以下语音识别文本：
1. 去除口语化填充词（嗯、啊、那个、就是说）
2. 修正明显的识别错误
3. 添加适当的标点符号
4. 保持原意不变

只返回清理后的文本，不要解释。"""


class VoiceCleanupTask(SideTask):
    @property
    def name(self) -> str:
        return "voice_cleanup"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        raw_text = ctx.config.get("_side_task_args", {}).get("raw_text", "")
        # 类型校验：raw_text 必须是 str
        if not isinstance(raw_text, str):
            logger.warning(
                "VoiceCleanupTask: raw_text 类型无效 (%s)，期望 str",
                type(raw_text).__name__,
            )
            return None
        if not raw_text or len(raw_text) < 3:
            return raw_text
        try:
            response = await ctx.llm_client.chat(
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": raw_text},
                ],
                model=ctx.side_model,
            )
            return _strip_control_chars(response.content).strip() if response.content else raw_text
        except Exception:
            logger.warning("VoiceCleanupTask 执行失败", exc_info=True)
            return raw_text
