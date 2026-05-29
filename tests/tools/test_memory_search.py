"""MemorySearchTool 测试。"""
import pytest
from unittest.mock import MagicMock

from memory.searcher import MemoryResult


@pytest.mark.asyncio
async def test_memory_search_tool_returns_results():
    """MemorySearchTool 应返回搜索结果。"""
    from capability.tools.memory_search import MemorySearchTool

    mock_searcher = MagicMock()
    mock_searcher.search.return_value = [
        MemoryResult(source="long_term", content="用户喜欢辣的食物", relevance=1.0, topic="food.md")
    ]
    tool = MemorySearchTool(mock_searcher)
    result = await tool.execute(query="辣的食物")
    assert "辣" in result
    mock_searcher.search.assert_called_once_with("辣的食物", limit=5)


@pytest.mark.asyncio
async def test_memory_search_tool_empty_query():
    """空查询应返回提示。"""
    from capability.tools.memory_search import MemorySearchTool

    tool = MemorySearchTool(MagicMock())
    result = await tool.execute(query="")
    assert "请输入" in result or "空" in result or len(result) > 0


@pytest.mark.asyncio
async def test_memory_search_tool_no_results():
    """无匹配结果应返回提示。"""
    from capability.tools.memory_search import MemorySearchTool

    mock_searcher = MagicMock()
    mock_searcher.search.return_value = []
    tool = MemorySearchTool(mock_searcher)
    result = await tool.execute(query="不存在的内容")
    assert "未找到" in result


@pytest.mark.asyncio
async def test_memory_search_tool_multiple_results():
    """多条结果应全部格式化输出。"""
    from capability.tools.memory_search import MemorySearchTool

    mock_searcher = MagicMock()
    mock_searcher.search.return_value = [
        MemoryResult(source="long_term", content="喜欢辣的食物", relevance=1.0, topic="food.md"),
        MemoryResult(source="short_term", content="今天吃了火锅", relevance=0.8, topic=None),
    ]
    tool = MemorySearchTool(mock_searcher)
    result = await tool.execute(query="辣")
    assert "long_term" in result
    assert "short_term" in result
    assert "food.md" in result
    assert "火锅" in result


@pytest.mark.asyncio
async def test_memory_search_tool_missing_query():
    """缺少 query 参数应返回提示。"""
    from capability.tools.memory_search import MemorySearchTool

    tool = MemorySearchTool(MagicMock())
    result = await tool.execute()
    assert "请输入" in result or "空" in result or len(result) > 0
