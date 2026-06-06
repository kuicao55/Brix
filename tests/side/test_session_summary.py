"""SessionSummaryTask 改造测试 — 事件摘要 + 短期记忆写入 + 幂等性。"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from side.base import SideTaskContext
from side.tasks.session_summary import SessionSummaryTask


def _make_ctx_with_memory(
    llm_response: str = "",
    session_messages: list | None = None,
    session_id: str = "test-session-001",
    existing_items: list | None = None,
    short_term_available: bool = True,
) -> SideTaskContext:
    """创建带 memory mock 的 SideTaskContext。"""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = llm_response
    mock_client.chat = AsyncMock(return_value=mock_response)

    # 构建 memory mock
    mock_memory = MagicMock()
    mock_memory.current_session_id = session_id

    # short_term mock
    if short_term_available:
        mock_st = MagicMock()
        mock_st.get_by_session = MagicMock(return_value=existing_items or [])
        mock_st.add_item = MagicMock()
        mock_memory.short_term = mock_st
    else:
        mock_memory.short_term = None

    # list_sessions 返回 session 索引（含 created 日期）
    mock_memory.list_sessions = MagicMock(return_value=[
        {"id": session_id, "created": "2025-06-05T10:00:00+00:00"},
    ])

    return SideTaskContext(
        llm_client=mock_client,
        side_model="test-model",
        config={},
        memory=mock_memory,
        session_messages=session_messages or [],
        user_input="",
        hooks=None,
    )


# --- 核心功能测试 ---


@pytest.mark.asyncio
async def test_session_summary_generates_and_writes():
    """SessionSummaryTask 生成摘要并写入短期记忆。"""
    task = SessionSummaryTask()
    ctx = _make_ctx_with_memory(
        llm_response="用户在开发 Python CLI 项目，完成了记忆系统重构。下一步是实现退出路径的摘要保存。",
        session_messages=[
            {"role": "user", "content": "帮我重构记忆系统"},
            {"role": "assistant", "content": "好的，我来帮你重构"},
            {"role": "user", "content": "继续"},
        ],
    )
    result = await task.execute(ctx)

    # 应返回摘要文本
    assert result is not None
    assert "Python" in result or "记忆" in result

    # 应写入短期记忆
    ctx.memory.short_term.add_item.assert_called_once()
    call_kwargs = ctx.memory.short_term.add_item.call_args
    assert call_kwargs.kwargs.get("source") == "side_summary" or call_kwargs[1].get("source") == "side_summary"
    assert call_kwargs.kwargs.get("type") == "event" or call_kwargs[1].get("type") == "event"
    assert call_kwargs.kwargs.get("session_id") == "test-session-001" or call_kwargs[1].get("session_id") == "test-session-001"


@pytest.mark.asyncio
async def test_session_summary_uses_session_start_date():
    """SessionSummaryTask 使用 session 开始日期作为 date 参数。"""
    task = SessionSummaryTask()
    ctx = _make_ctx_with_memory(
        llm_response="用户在调试登录问题。",
        session_messages=[
            {"role": "user", "content": "登录有 bug"},
        ],
    )
    await task.execute(ctx)

    call_kwargs = ctx.memory.short_term.add_item.call_args
    # date 应为 session 开始日期（从 list_sessions 的 created 字段提取）
    date = call_kwargs.kwargs.get("date") or call_kwargs[1].get("date")
    assert date == "2025-06-05"


@pytest.mark.asyncio
async def test_session_summary_empty_messages_returns_none():
    """SessionSummaryTask 无消息时返回 None，不写入记忆。"""
    task = SessionSummaryTask()
    ctx = _make_ctx_with_memory(session_messages=[])
    result = await task.execute(ctx)

    assert result is None
    ctx.memory.short_term.add_item.assert_not_called()


@pytest.mark.asyncio
async def test_session_summary_no_session_id_returns_none():
    """SessionSummaryTask 无 session_id 时返回 None。"""
    task = SessionSummaryTask()
    ctx = _make_ctx_with_memory(
        llm_response="摘要内容",
        session_messages=[{"role": "user", "content": "hi"}],
    )
    ctx.memory.current_session_id = None
    result = await task.execute(ctx)

    assert result is None


# --- 幂等性测试 ---


@pytest.mark.asyncio
async def test_session_summary_idempotent_skips_if_exists():
    """SessionSummaryTask 幂等：session 已有 type=event 的摘要时跳过。"""
    task = SessionSummaryTask()
    # 已有 event 类型的 item
    existing = [
        {"id": "existing-1", "type": "event", "source": "side_summary",
         "content": "之前的摘要", "session_id": "test-session-001",
         "created": "2025-06-05T10:00:00+00:00"},
    ]
    ctx = _make_ctx_with_memory(
        llm_response="新摘要",
        session_messages=[
            {"role": "user", "content": "hi"},
        ],
        existing_items=existing,
    )
    result = await task.execute(ctx)

    # 应跳过，不生成新摘要
    assert result is None
    ctx.llm_client.chat.assert_not_called()
    ctx.memory.short_term.add_item.assert_not_called()


@pytest.mark.asyncio
async def test_session_summary_idempotent_allows_non_event_items():
    """SessionSummaryTask 幂等：session 有非 event 类型的 item 时仍生成摘要。"""
    task = SessionSummaryTask()
    # 只有 note 类型的 item，没有 event
    existing = [
        {"id": "note-1", "type": "note", "source": "user",
         "content": "笔记", "session_id": "test-session-001",
         "created": "2025-06-05T10:00:00+00:00"},
    ]
    ctx = _make_ctx_with_memory(
        llm_response="用户在开发项目。",
        session_messages=[
            {"role": "user", "content": "帮我写代码"},
        ],
        existing_items=existing,
    )
    result = await task.execute(ctx)

    # 应生成摘要（非 event 类型不算幂等）
    assert result is not None
    ctx.memory.short_term.add_item.assert_called_once()


# --- 降级测试 ---


@pytest.mark.asyncio
async def test_session_summary_no_short_term_returns_summary_only():
    """short_term 不可用时返回摘要但不写入。"""
    task = SessionSummaryTask()
    ctx = _make_ctx_with_memory(
        llm_response="用户在学习 Python。",
        session_messages=[
            {"role": "user", "content": "教我 Python"},
        ],
        short_term_available=False,
    )
    result = await task.execute(ctx)

    # 应返回摘要
    assert result is not None
    assert "Python" in result


@pytest.mark.asyncio
async def test_session_summary_llm_failure_returns_none():
    """LLM 调用失败时返回 None。"""
    task = SessionSummaryTask()
    ctx = _make_ctx_with_memory(
        session_messages=[
            {"role": "user", "content": "hi"},
        ],
    )
    ctx.llm_client.chat = AsyncMock(side_effect=RuntimeError("LLM down"))
    result = await task.execute(ctx)

    assert result is None
    ctx.memory.short_term.add_item.assert_not_called()


@pytest.mark.asyncio
async def test_session_summary_llm_returns_empty():
    """LLM 返回空内容时返回 None。"""
    task = SessionSummaryTask()
    ctx = _make_ctx_with_memory(
        llm_response="",
        session_messages=[
            {"role": "user", "content": "hi"},
        ],
    )
    result = await task.execute(ctx)

    assert result is None


# --- SideTaskManager.generate_session_summary 测试 ---


@pytest.mark.asyncio
async def test_manager_generate_session_summary_calls_task():
    """SideTaskManager.generate_session_summary 调用 session_summary task。"""
    from side.manager import SideTaskManager

    mgr = SideTaskManager()
    mock_memory = MagicMock()
    mock_memory.current_session_id = "sess-123"
    mock_memory.load_session = MagicMock(return_value=[
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ])
    mock_memory.short_term = MagicMock()
    mock_memory.short_term.get_by_session = MagicMock(return_value=[])
    mock_memory.list_sessions = MagicMock(return_value=[
        {"id": "sess-123", "created": "2025-06-05T10:00:00+00:00"},
    ])

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "用户在打招呼。"
    mock_llm.chat = AsyncMock(return_value=mock_response)

    mgr.configure(
        config={"side": {"enabled": True, "model": "test-model",
                         "tasks": {"session_summary": {"enabled": True}}}},
        llm_client=mock_llm,
        memory=mock_memory,
    )
    mgr.register(SessionSummaryTask())

    result = await mgr.generate_session_summary()
    assert result is not None
    mock_memory.short_term.add_item.assert_called_once()


@pytest.mark.asyncio
async def test_manager_generate_session_summary_no_session():
    """无当前 session 时返回 None。"""
    from side.manager import SideTaskManager

    mgr = SideTaskManager()
    mock_memory = MagicMock()
    mock_memory.current_session_id = None

    mgr.configure(
        config={"side": {"enabled": True, "model": "test-model",
                         "tasks": {"session_summary": {"enabled": True}}}},
        llm_client=MagicMock(),
        memory=mock_memory,
    )
    mgr.register(SessionSummaryTask())

    result = await mgr.generate_session_summary()
    assert result is None
