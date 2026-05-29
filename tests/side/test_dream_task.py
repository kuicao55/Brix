"""DreamTask 单元测试。"""
from __future__ import annotations

import types

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_dream_task_skips_when_not_ready():
    """未达门槛时应跳过。"""
    from side.tasks.dream import DreamTask

    task = DreamTask()
    mock_dm = MagicMock()
    mock_dm.should_dream.return_value = False
    mock_memory = MagicMock()
    mock_memory.dream = mock_dm
    ctx = types.SimpleNamespace(
        llm_client=MagicMock(),
        side_model="test/model",
        config={},
        memory=mock_memory,
        session_messages=(),
        user_input="hi",
        hooks=MagicMock(),
    )
    result = await task.execute(ctx)
    assert result is None


@pytest.mark.asyncio
async def test_dream_task_runs_when_ready():
    """满足门槛时应执行蒸馏。"""
    from side.tasks.dream import DreamTask

    task = DreamTask()
    mock_dm = MagicMock()
    mock_dm.should_dream.return_value = True
    mock_dm.run = AsyncMock()
    mock_memory = MagicMock()
    mock_memory.dream = mock_dm
    ctx = types.SimpleNamespace(
        llm_client=MagicMock(),
        side_model="test/model",
        config={},
        memory=mock_memory,
        session_messages=(),
        user_input="hi",
        hooks=MagicMock(),
    )
    result = await task.execute(ctx)
    mock_dm.run.assert_called_once()


@pytest.mark.asyncio
async def test_dream_task_handles_no_dream_manager():
    """没有 DreamManager 时应安全跳过。"""
    from side.tasks.dream import DreamTask

    task = DreamTask()
    mock_memory = MagicMock()
    mock_memory.dream = None
    ctx = types.SimpleNamespace(
        llm_client=MagicMock(),
        side_model="test/model",
        config={},
        memory=mock_memory,
        session_messages=(),
        user_input="hi",
        hooks=MagicMock(),
    )
    result = await task.execute(ctx)
    assert result is None
