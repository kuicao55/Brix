"""SaveMemoryTool 单元测试。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from capability.tools.save_memory import SaveMemoryTool
from memory.short_term import ShortTermMemory


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """临时数据目录。"""
    return tmp_path / "data"


@pytest.fixture
def short_term(data_dir: Path) -> ShortTermMemory:
    """初始化 ShortTermMemory。"""
    return ShortTermMemory(data_dir)


@pytest.fixture
def mock_provider() -> MagicMock:
    """模拟 MemoryProvider，返回固定 session_id。"""
    provider = MagicMock()
    provider.current_session_id = "test-session-uuid"
    provider.list_sessions.return_value = [
        {"id": "test-session-uuid", "created": "2026-06-06T10:00:00+00:00"},
    ]
    return provider


@pytest.fixture
def tool(short_term: ShortTermMemory, mock_provider: MagicMock) -> SaveMemoryTool:
    """初始化 SaveMemoryTool。"""
    return SaveMemoryTool(short_term=short_term, memory_provider=mock_provider)


class TestSaveMemoryToolSchema:
    """测试工具元数据。"""

    def test_name(self, tool: SaveMemoryTool) -> None:
        assert tool.name == "save_memory"

    def test_description_is_nonempty(self, tool: SaveMemoryTool) -> None:
        assert len(tool.description) > 0

    def test_input_schema_has_required_fields(self, tool: SaveMemoryTool) -> None:
        schema = tool.input_schema
        assert schema["type"] == "object"
        required = schema["required"]
        assert "type" in required
        assert "category" in required
        assert "content" in required

    def test_input_schema_type_enum(self, tool: SaveMemoryTool) -> None:
        type_prop = tool.input_schema["properties"]["type"]
        assert set(type_prop["enum"]) == {"preference", "fact", "emotion", "task", "reflection"}

    def test_input_schema_category_enum(self, tool: SaveMemoryTool) -> None:
        cat_prop = tool.input_schema["properties"]["category"]
        assert set(cat_prop["enum"]) == {"user", "self"}


class TestSaveMemoryToolValidation:
    """测试参数校验。"""

    @pytest.mark.asyncio
    async def test_invalid_type(self, tool: SaveMemoryTool) -> None:
        result = await tool.execute(type="invalid", category="user", content="test")
        assert "参数错误" in result or "错误" in result

    @pytest.mark.asyncio
    async def test_invalid_category(self, tool: SaveMemoryTool) -> None:
        result = await tool.execute(type="preference", category="admin", content="test")
        assert "参数错误" in result or "错误" in result

    @pytest.mark.asyncio
    async def test_empty_content(self, tool: SaveMemoryTool) -> None:
        result = await tool.execute(type="fact", category="user", content="")
        assert "参数错误" in result or "错误" in result or "不能为空" in result

    @pytest.mark.asyncio
    async def test_whitespace_only_content(self, tool: SaveMemoryTool) -> None:
        result = await tool.execute(type="fact", category="user", content="   ")
        assert "参数错误" in result or "错误" in result or "不能为空" in result

    @pytest.mark.asyncio
    async def test_content_too_long(self, tool: SaveMemoryTool) -> None:
        long_content = "a" * 501
        result = await tool.execute(type="fact", category="user", content=long_content)
        assert "参数错误" in result or "错误" in result or "500" in result

    @pytest.mark.asyncio
    async def test_content_at_500_chars_ok(self, tool: SaveMemoryTool) -> None:
        content = "b" * 500
        result = await tool.execute(type="fact", category="user", content=content)
        assert "已保存" in result or "成功" in result

    @pytest.mark.asyncio
    async def test_missing_type(self, tool: SaveMemoryTool) -> None:
        result = await tool.execute(category="user", content="test")
        assert "参数错误" in result or "错误" in result or "缺少" in result

    @pytest.mark.asyncio
    async def test_missing_content(self, tool: SaveMemoryTool) -> None:
        result = await tool.execute(type="fact", category="user")
        assert "参数错误" in result or "错误" in result or "缺少" in result


class TestSaveMemoryToolWrite:
    """测试实际写入。"""

    @pytest.mark.asyncio
    async def test_writes_item_to_short_term(
        self, tool: SaveMemoryTool, short_term: ShortTermMemory, data_dir: Path
    ) -> None:
        result = await tool.execute(
            type="preference", category="user", content="喜欢用 Python"
        )
        assert "已保存" in result or "成功" in result

        # 读取 session 开始日期的文件验证写入
        items = short_term.get_recent(limit=10)
        assert len(items) >= 1
        saved = items[0]
        assert saved["content"] == "喜欢用 Python"
        assert saved["type"] == "preference"
        assert saved["category"] == "user"
        assert saved["session_id"] == "test-session-uuid"
        assert saved["source"] == "save_memory"

    @pytest.mark.asyncio
    async def test_writes_with_context(
        self, tool: SaveMemoryTool, short_term: ShortTermMemory
    ) -> None:
        await tool.execute(
            type="emotion", category="self", content="感到开心", context="用户夸了我"
        )
        items = short_term.get_recent(limit=10)
        saved = items[0]
        assert saved["context"] == "用户夸了我"

    @pytest.mark.asyncio
    async def test_writes_without_context(
        self, tool: SaveMemoryTool, short_term: ShortTermMemory
    ) -> None:
        await tool.execute(type="task", category="user", content="需要买菜")
        items = short_term.get_recent(limit=10)
        saved = items[0]
        assert saved["context"] == ""

    @pytest.mark.asyncio
    async def test_date_from_session_created(
        self, tool: SaveMemoryTool, short_term: ShortTermMemory
    ) -> None:
        """验证 date 取 session 的 created 日期。"""
        await tool.execute(type="fact", category="user", content="test fact")
        # session created = "2026-06-06T10:00:00+00:00" -> date = "2026-06-06"
        items = short_term.get_by_date("2026-06-06")
        assert len(items) >= 1
        assert items[0]["content"] == "test fact"

    @pytest.mark.asyncio
    async def test_no_session_returns_error(
        self, short_term: ShortTermMemory
    ) -> None:
        """无活跃 session 时应返回错误。"""
        provider = MagicMock()
        provider.current_session_id = None
        tool = SaveMemoryTool(short_term=short_term, memory_provider=provider)
        result = await tool.execute(type="fact", category="user", content="test")
        assert "错误" in result or "session" in result.lower()

    @pytest.mark.asyncio
    async def test_session_not_in_index_returns_error(
        self, short_term: ShortTermMemory
    ) -> None:
        """session 不在索引中时应返回错误。"""
        provider = MagicMock()
        provider.current_session_id = "unknown-session"
        provider.list_sessions.return_value = []
        tool = SaveMemoryTool(short_term=short_term, memory_provider=provider)
        result = await tool.execute(type="fact", category="user", content="test")
        assert "错误" in result or "session" in result.lower()

    @pytest.mark.asyncio
    async def test_all_valid_types(
        self, tool: SaveMemoryTool, short_term: ShortTermMemory
    ) -> None:
        """所有合法 type 都应写入成功。"""
        for item_type in ("preference", "fact", "emotion", "task", "reflection"):
            result = await tool.execute(
                type=item_type, category="user", content=f"test {item_type}"
            )
            assert "已保存" in result or "成功" in result
        items = short_term.get_recent(limit=10)
        assert len(items) == 5
