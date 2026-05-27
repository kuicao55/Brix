"""Side tasks 单元测试。"""
from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from side.base import SideTaskContext


def _make_ctx(llm_response: str = "", **kwargs) -> SideTaskContext:
    """创建测试用 SideTaskContext。"""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = llm_response
    mock_client.chat = AsyncMock(return_value=mock_response)
    return SideTaskContext(
        llm_client=mock_client,
        side_model="test-model",
        config=kwargs.get("config", {}),
        memory=kwargs.get("memory"),
        session_messages=kwargs.get("session_messages", []),
        user_input=kwargs.get("user_input", ""),
        hooks=kwargs.get("hooks"),
    )


# --- SessionTitleTask ---


@pytest.mark.asyncio
async def test_session_title_basic():
    """SessionTitleTask 从对话中提取标题。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(
        llm_response='{"title": "Fix login bug"}',
        session_messages=[
            {"role": "user", "content": "登录页面有个 bug"},
            {"role": "assistant", "content": "我来看看"},
            {"role": "user", "content": "点击登录按钮没反应"},
        ],
    )
    result = await task.execute(ctx)
    assert result == "Fix login bug"
    ctx.llm_client.chat.assert_called_once()


@pytest.mark.asyncio
async def test_session_title_empty_messages():
    """SessionTitleTask 无用户消息时返回 None。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(session_messages=[])
    result = await task.execute(ctx)
    assert result is None


@pytest.mark.asyncio
async def test_session_title_invalid_json():
    """SessionTitleTask JSON 解析失败时回退到首条用户消息。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(
        llm_response="not json",
        session_messages=[{"role": "user", "content": "hi"}],
    )
    result = await task.execute(ctx)
    # 回退：取首条用户消息前 80 字符
    assert result == "hi"


@pytest.mark.asyncio
async def test_session_title_fenced_json():
    """SessionTitleTask 能从 ```json fenced 代码块中提取标题。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    fenced = '```json\n{"title": "Fix auth flow"}\n```'
    ctx = _make_ctx(
        llm_response=fenced,
        session_messages=[{"role": "user", "content": "auth broken"}],
    )
    result = await task.execute(ctx)
    assert result == "Fix auth flow"


@pytest.mark.asyncio
async def test_session_title_prefixed_text():
    """SessionTitleTask 能从带前缀文字的响应中提取标题。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(
        llm_response='Here is the title:\n{"title": "Debug CI pipeline"}',
        session_messages=[{"role": "user", "content": "CI broken"}],
    )
    result = await task.execute(ctx)
    assert result == "Debug CI pipeline"


@pytest.mark.asyncio
async def test_session_title_oversized_trimmed():
    """SessionTitleTask 标题超长时截断到 80 字符。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    long_title = "A" * 120
    ctx = _make_ctx(
        llm_response=json.dumps({"title": long_title}),
        session_messages=[{"role": "user", "content": "x"}],
    )
    result = await task.execute(ctx)
    assert result is not None
    assert len(result) <= 80


@pytest.mark.asyncio
async def test_session_title_newlines_collapsed():
    """SessionTitleTask 标题含换行时折叠为单行。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(
        llm_response=json.dumps({"title": "Fix\nlogin\nbug"}),
        session_messages=[{"role": "user", "content": "x"}],
    )
    result = await task.execute(ctx)
    assert result is not None
    assert "\n" not in result
    assert "Fix login bug" == result


@pytest.mark.asyncio
async def test_session_title_non_string_field():
    """SessionTitleTask title 字段非字符串时回退。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(
        llm_response='{"title": 12345}',
        session_messages=[{"role": "user", "content": "help me"}],
    )
    result = await task.execute(ctx)
    # 非字符串 title 视为无效，回退到首条用户消息
    assert result == "help me"


@pytest.mark.asyncio
async def test_session_title_fallback_long_message():
    """SessionTitleTask 回退时截断首条用户消息到 80 字符。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    long_msg = "请帮我修复一个很长很长的问题" * 20
    ctx = _make_ctx(
        llm_response="totally broken response",
        session_messages=[{"role": "user", "content": long_msg}],
    )
    result = await task.execute(ctx)
    assert result is not None
    assert len(result) <= 80


# --- ToolSummaryTask ---


@pytest.mark.asyncio
async def test_tool_summary_basic():
    """ToolSummaryTask 生成工具调用摘要。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Searched in auth/",
        config={
            "_side_task_args": {
                "tool_name": "Grep",
                "tool_input": {"pattern": "auth"},
                "tool_result": "found 3 files",
            },
        },
    )
    result = await task.execute(ctx)
    assert result == "Searched in auth/"


@pytest.mark.asyncio
async def test_tool_summary_empty_args():
    """ToolSummaryTask 无工具信息时仍可执行。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(llm_response="No tools used", config={})
    result = await task.execute(ctx)
    assert result == "No tools used"


@pytest.mark.asyncio
async def test_tool_summary_string_input():
    """ToolSummaryTask tool_input 为字符串时不崩溃。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Read file",
        config={
            "_side_task_args": {
                "tool_name": "Read",
                "tool_input": "/path/to/file.py",
                "tool_result": "file contents",
            },
        },
    )
    result = await task.execute(ctx)
    assert result == "Read file"


@pytest.mark.asyncio
async def test_tool_summary_list_input():
    """ToolSummaryTask tool_input 为列表时不崩溃。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Processed items",
        config={
            "_side_task_args": {
                "tool_name": "Process",
                "tool_input": ["item1", "item2", "item3"],
                "tool_result": "done",
            },
        },
    )
    result = await task.execute(ctx)
    assert result == "Processed items"


@pytest.mark.asyncio
async def test_tool_summary_scalar_input():
    """ToolSummaryTask tool_input 为标量（int）时不崩溃。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Incremented",
        config={
            "_side_task_args": {
                "tool_name": "Counter",
                "tool_input": 42,
                "tool_result": 43,
            },
        },
    )
    result = await task.execute(ctx)
    assert result == "Incremented"


@pytest.mark.asyncio
async def test_tool_summary_none_input():
    """ToolSummaryTask tool_input 为 None 时不崩溃。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="No input",
        config={
            "_side_task_args": {
                "tool_name": "Ping",
                "tool_input": None,
                "tool_result": "pong",
            },
        },
    )
    result = await task.execute(ctx)
    assert result == "No input"


@pytest.mark.asyncio
async def test_tool_summary_oversized_trimmed():
    """ToolSummaryTask 输出超长时截断到 30 字符。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    long_output = "This is a very long summary that exceeds the thirty character limit significantly"
    ctx = _make_ctx(
        llm_response=long_output,
        config={
            "_side_task_args": {
                "tool_name": "Grep",
                "tool_input": {"pattern": "auth"},
                "tool_result": "found",
            },
        },
    )
    result = await task.execute(ctx)
    assert result is not None
    assert len(result) <= 30


@pytest.mark.asyncio
async def test_tool_summary_newlines_collapsed():
    """ToolSummaryTask 输出含换行时折叠为单行。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    ctx = _make_ctx(
        llm_response="Fixed\nbug\nin auth",
        config={
            "_side_task_args": {
                "tool_name": "Edit",
                "tool_input": {"file": "auth.py"},
                "tool_result": "ok",
            },
        },
    )
    result = await task.execute(ctx)
    assert result is not None
    assert "\n" not in result
    assert "Fixed bug in auth" == result


@pytest.mark.asyncio
async def test_tool_summary_non_string_output():
    """ToolSummaryTask 输出非字符串时回退到 None。"""
    from side.tasks.tool_summary import ToolSummaryTask

    task = ToolSummaryTask()
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = None
    mock_client.chat = AsyncMock(return_value=mock_response)
    ctx = SideTaskContext(
        llm_client=mock_client,
        side_model="test-model",
        config={
            "_side_task_args": {
                "tool_name": "Grep",
                "tool_input": {"pattern": "auth"},
                "tool_result": "found",
            },
        },
        memory=None,
        session_messages=[],
        user_input="",
        hooks=None,
    )
    result = await task.execute(ctx)
    assert result is None
