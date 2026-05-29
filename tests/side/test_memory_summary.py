"""MemorySummaryTask 单元测试。"""
from __future__ import annotations

import types

import pytest
from unittest.mock import MagicMock

from side.base import SideTaskContext


def _make_ctx(**kwargs) -> SideTaskContext:
    """创建测试用 SideTaskContext。"""
    return SideTaskContext(
        llm_client=kwargs.get("llm_client", MagicMock()),
        side_model=kwargs.get("side_model", "test-model"),
        config=kwargs.get("config", {}),
        memory=kwargs.get("memory"),
        session_messages=kwargs.get("session_messages", []),
        user_input=kwargs.get("user_input", ""),
        hooks=kwargs.get("hooks"),
    )


@pytest.mark.asyncio
async def test_memory_summary_returns_summary():
    """MemorySummaryTask 应返回近期记忆摘要。"""
    from side.tasks.memory_summary import MemorySummaryTask

    task = MemorySummaryTask()

    mock_stm = MagicMock()
    mock_stm.get_recent.return_value = [
        {"content": "用户喜欢辣的食物", "source": "pref_detection", "created": "2026-05-29"},
        {"content": "用户天天自己做饭", "source": "pref_detection", "created": "2026-05-29"},
    ]
    mock_memory = MagicMock()
    mock_memory.short_term = mock_stm

    ctx = _make_ctx(
        session_messages=[{"role": "user", "content": "你好"}],
        memory=mock_memory,
    )
    result = await task.execute(ctx)

    assert result is not None
    assert len(result) > 0
    # 摘要应包含短期记忆中的关键内容
    assert "辣" in result or "做饭" in result


@pytest.mark.asyncio
async def test_memory_summary_returns_none_when_empty():
    """无短期记忆时应返回 None。"""
    from side.tasks.memory_summary import MemorySummaryTask

    task = MemorySummaryTask()

    mock_stm = MagicMock()
    mock_stm.get_recent.return_value = []
    mock_memory = MagicMock()
    mock_memory.short_term = mock_stm

    ctx = _make_ctx(
        session_messages=[{"role": "user", "content": "你好"}],
        memory=mock_memory,
    )
    result = await task.execute(ctx)

    assert result is None


@pytest.mark.asyncio
async def test_memory_summary_returns_none_when_no_memory():
    """ctx.memory 为 None 时应返回 None。"""
    from side.tasks.memory_summary import MemorySummaryTask

    task = MemorySummaryTask()
    ctx = _make_ctx(memory=None)
    result = await task.execute(ctx)

    assert result is None


@pytest.mark.asyncio
async def test_memory_summary_returns_none_when_no_short_term():
    """memory 无 short_term 属性时应返回 None。"""
    from side.tasks.memory_summary import MemorySummaryTask

    task = MemorySummaryTask()
    mock_memory = MagicMock(spec=[])  # 无任何属性
    ctx = _make_ctx(memory=mock_memory)
    result = await task.execute(ctx)

    assert result is None


@pytest.mark.asyncio
async def test_memory_summary_name():
    """MemorySummaryTask.name 应返回 'memory_summary'。"""
    from side.tasks.memory_summary import MemorySummaryTask

    task = MemorySummaryTask()
    assert task.name == "memory_summary"
