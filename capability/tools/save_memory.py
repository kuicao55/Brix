"""SaveMemoryTool — 主模型主动写入短期记忆。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from capability.base import Tool

logger = logging.getLogger(__name__)

# 允许的记忆类型
_ALLOWED_TYPES = ("preference", "fact", "emotion", "task", "reflection")
# 允许的分类
_ALLOWED_CATEGORIES = ("user", "self")
# content 最大长度
_MAX_CONTENT_LENGTH = 500


class SaveMemoryTool(Tool):
    """将用户偏好、事实、情绪、任务或反思写入短期记忆。

    支持两种模式：
    1. 直接绑定 short_term 和 memory_provider（旧模式，兼容 CLI）
    2. 通过 server_app 获取 per-connection memory（新模式，Server 端）
    """

    def __init__(self, short_term: Any = None, memory_provider: Any = None, server_app: Any = None) -> None:
        """
        Args:
            short_term: ShortTermMemory 实例，提供 add_item() 方法。
            memory_provider: BrixMemoryProvider 实例，提供 current_session_id 和 list_sessions()。
            server_app: BrixServerApp 实例，用于获取 per-connection memory。
        """
        self._short_term = short_term
        self._provider = memory_provider
        self._server_app = server_app

    @property
    def name(self) -> str:
        return "save_memory"

    @property
    def description(self) -> str:
        return "将用户偏好、事实、情绪、任务或反思写入记忆。type 可选: preference/fact/emotion/task/reflection。category: user(用户信息)/self(自我反思)。"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "记忆类型",
                    "enum": list(_ALLOWED_TYPES),
                },
                "category": {
                    "type": "string",
                    "description": "分类：user=用户信息，self=自我反思",
                    "enum": list(_ALLOWED_CATEGORIES),
                },
                "content": {
                    "type": "string",
                    "description": "记忆内容，不超过 500 字符",
                },
                "context": {
                    "type": "string",
                    "description": "可选上下文信息",
                },
            },
            "required": ["type", "category", "content"],
        }

    def _get_memory(self, client_id: str = "") -> tuple[Any, Any]:
        """获取 (short_term, provider) 实例。"""
        if self._short_term and self._provider:
            return self._short_term, self._provider
        if self._server_app and client_id:
            ctx = self._server_app.get_session_context(client_id)
            if ctx:
                return ctx.memory.short_term, ctx.memory
        return None, None

    async def execute(self, **params: Any) -> str:
        # 1. 提取参数
        item_type = params.get("type")
        category = params.get("category")
        content = params.get("content")
        context = params.get("context", "")
        client_id = params.get("client_id", "")

        # 2. 校验必填参数
        if not item_type:
            return "参数错误：缺少 type。"
        if not category:
            return "参数错误：缺少 category。"
        if content is None:
            return "参数错误：缺少 content。"

        # 3. 校验 type 枚举
        if item_type not in _ALLOWED_TYPES:
            return f"参数错误：type 必须是 {', '.join(_ALLOWED_TYPES)} 之一。"

        # 4. 校验 category 枚举
        if category not in _ALLOWED_CATEGORIES:
            return f"参数错误：category 必须是 {', '.join(_ALLOWED_CATEGORIES)} 之一。"

        # 5. 校验 content
        if not isinstance(content, str):
            return "参数错误：content 必须是字符串。"
        content = content.strip()
        if not content:
            return "参数错误：content 不能为空。"
        if len(content) > _MAX_CONTENT_LENGTH:
            return f"参数错误：content 不能超过 {_MAX_CONTENT_LENGTH} 个字符。"

        # 6. 获取 memory 实例
        short_term, provider = self._get_memory(client_id)
        if not short_term or not provider:
            return "错误：记忆功能不可用。"

        # 7. 获取当前 session 信息
        session_id = provider.current_session_id
        if not session_id:
            return "错误：当前无活跃 session，无法保存记忆。"

        # 8. 从 session 索引中查找 session 开始日期（降级到当天）
        date = self._resolve_session_date(session_id, provider)

        # 9. 写入短期记忆
        try:
            short_term.add_item(
                content=content,
                source="save_memory",
                date=date,
                type=item_type,
                category=category,
                session_id=session_id,
                context=context if isinstance(context, str) else "",
            )
            return f"已保存：[{item_type}] {content[:50]}"
        except Exception as e:
            logger.warning("SaveMemoryTool 写入失败: %s", e, exc_info=True)
            return "保存失败：写入记忆时发生内部错误，请稍后重试。"

    def _resolve_session_date(self, session_id: str, provider: Any = None) -> str:
        """从 session 索引中查找 session 的 created 日期，返回 YYYY-MM-DD。

        降级策略：查找失败时 fallback 到当天日期，不阻塞写入。
        """
        provider = provider or self._provider
        try:
            sessions = provider.list_sessions()
            for s in sessions:
                if s.get("id") == session_id:
                    created = s.get("created", "")
                    if isinstance(created, str) and len(created) >= 10:
                        return created[:10]
        except Exception as e:
            logger.warning("查询 session 索引失败，fallback 到当天日期: %s", e)
        # 降级：使用当天日期
        return datetime.now().strftime("%Y-%m-%d")
