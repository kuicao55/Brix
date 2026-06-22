"""记忆搜索工具。"""
from __future__ import annotations

from typing import Any

from capability.base import Tool


class MemorySearchTool(Tool):
    """搜索长期记忆，查找与当前话题相关的用户信息。"""

    def __init__(self, searcher: Any) -> None:
        self._searcher = searcher

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return "搜索长期记忆，查找与当前话题相关的用户信息"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **params: Any) -> str:
        # 1. 校验 query 类型
        query = params.get("query")
        if not isinstance(query, str):
            return "参数错误：query 必须是字符串。"
        query = query.strip()
        if not query:
            return "请输入搜索关键词。"

        # 2. 搜索 + 结果格式化，统一捕获异常
        try:
            results = self._searcher.search(query, limit=5)
            if not results:
                return "未找到相关记忆。"
            lines = []
            for r in results:
                try:
                    source = getattr(r, "source", "unknown")
                    topic = getattr(r, "topic", None)
                    content = getattr(r, "content", "")
                    prefix = f"[{source}]"
                    if topic:
                        prefix += f" ({topic})"
                    lines.append(f"{prefix} {str(content)[:200]}")
                except Exception:
                    # 单条结果格式化失败，跳过该条
                    continue
            return "\n".join(lines) if lines else "未找到相关记忆。"
        except Exception as e:
            return f"搜索失败：{e}"
