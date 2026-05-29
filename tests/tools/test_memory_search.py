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


# ── 对抗性测试（CQR: param/type validation + error handling） ──


@pytest.mark.asyncio
async def test_memory_search_tool_non_string_query_dict():
    """query 为 dict 时不应抛 AttributeError，应返回错误提示。"""
    from capability.tools.memory_search import MemorySearchTool

    tool = MemorySearchTool(MagicMock())
    result = await tool.execute(query={})
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_memory_search_tool_non_string_query_int():
    """query 为 int 时不应抛异常。"""
    from capability.tools.memory_search import MemorySearchTool

    tool = MemorySearchTool(MagicMock())
    result = await tool.execute(query=123)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_memory_search_tool_non_string_query_list():
    """query 为 list 时不应抛异常。"""
    from capability.tools.memory_search import MemorySearchTool

    tool = MemorySearchTool(MagicMock())
    result = await tool.execute(query=["a", "b"])
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_memory_search_tool_non_string_query_none():
    """query 为 None 时不应抛异常。"""
    from capability.tools.memory_search import MemorySearchTool

    tool = MemorySearchTool(MagicMock())
    result = await tool.execute(query=None)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_memory_search_tool_searcher_raises():
    """searcher.search() 抛异常时应返回稳定错误字符串，不能让异常传播。"""
    from capability.tools.memory_search import MemorySearchTool

    mock_searcher = MagicMock()
    mock_searcher.search.side_effect = RuntimeError("数据库连接失败")
    tool = MemorySearchTool(mock_searcher)
    result = await tool.execute(query="测试")
    assert isinstance(result, str)
    assert len(result) > 0
    # 不应包含 traceback，应是友好提示
    assert "Traceback" not in result


@pytest.mark.asyncio
async def test_memory_search_tool_malformed_result_missing_content():
    """结果条目缺少 content 属性时不应抛异常。"""
    from capability.tools.memory_search import MemorySearchTool

    bad_result = MagicMock()
    bad_result.source = "long_term"
    bad_result.topic = "test"
    del bad_result.content  # 模拟缺少 content

    mock_searcher = MagicMock()
    mock_searcher.search.return_value = [bad_result]
    tool = MemorySearchTool(mock_searcher)
    result = await tool.execute(query="测试")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_memory_search_tool_malformed_result_missing_source():
    """结果条目缺少 source 属性时不应抛异常。"""
    from capability.tools.memory_search import MemorySearchTool

    bad_result = MagicMock()
    bad_result.content = "一些内容"
    bad_result.topic = "test"
    del bad_result.source  # 模拟缺少 source

    mock_searcher = MagicMock()
    mock_searcher.search.return_value = [bad_result]
    tool = MemorySearchTool(mock_searcher)
    result = await tool.execute(query="测试")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_memory_search_tool_malformed_result_none_content():
    """结果条目 content 为 None 时不应抛异常。"""
    from capability.tools.memory_search import MemorySearchTool

    bad_result = MagicMock()
    bad_result.source = "long_term"
    bad_result.topic = None
    bad_result.content = None

    mock_searcher = MagicMock()
    mock_searcher.search.return_value = [bad_result]
    tool = MemorySearchTool(mock_searcher)
    result = await tool.execute(query="测试")
    assert isinstance(result, str)
    assert len(result) > 0
