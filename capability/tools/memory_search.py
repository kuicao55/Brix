"""记忆搜索工具。"""
from __future__ import annotations

from typing import Any

from capability.base import Tool


class MemorySearchTool(Tool):
    """搜索长期记忆，查找与当前话题相关的用户信息。

    支持两种模式：
    1. 直接绑定 searcher（旧模式，兼容 CLI）
    2. 通过 server_app 获取 per-connection memory（新模式，Server 端）
    """

    def __init__(self, searcher: Any = None, server_app: Any = None) -> None:
        self._searcher = searcher
        self._server_app = server_app

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

    def _get_searcher(self, client_id: str = "") -> Any:
        """获取 searcher 实例。"""
        if self._searcher:
            return self._searcher
        if self._server_app and client_id:
            ctx = self._server_app.get_session_context(client_id)
            if ctx and ctx.memory.searcher:
                return ctx.memory.searcher
        return None

    async def execute(self, **params: Any) -> str:
        # 1. 校验 query 类型
        query = params.get("query")
        if not isinstance(query, str):
            return "参数错误：query 必须是字符串。"
        query = query.strip()
        if not query:
            return "请输入搜索关键词。"

        # 2. 获取 searcher
        client_id = params.get("client_id", "")
        searcher = self._get_searcher(client_id)
        if not searcher:
            return "错误：记忆搜索功能不可用。"

        # 3. 搜索 + 结果格式化，统一捕获异常
        try:
            results = searcher.search(query, limit=5)
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
