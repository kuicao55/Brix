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
        query = params.get("query", "").strip()
        if not query:
            return "请输入搜索关键词。"
        results = self._searcher.search(query, limit=5)
        if not results:
            return "未找到相关记忆。"
        lines = []
        for r in results:
            prefix = f"[{r.source}]"
            if r.topic:
                prefix += f" ({r.topic})"
            lines.append(f"{prefix} {r.content[:200]}")
        return "\n".join(lines)
