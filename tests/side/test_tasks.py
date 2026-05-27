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
    """SessionTitleTask JSON 解析失败时返回 None。"""
    from side.tasks.session_title import SessionTitleTask

    task = SessionTitleTask()
    ctx = _make_ctx(
        llm_response="not json",
        session_messages=[{"role": "user", "content": "hi"}],
    )
    result = await task.execute(ctx)
    assert result is None


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
