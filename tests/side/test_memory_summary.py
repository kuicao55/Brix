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


# --- CQR: Provider initialization resilience on filesystem errors ---


class TestProviderResilientInit:
    """BrixMemoryProvider 初始化应在存储组件抛异常时优雅降级。"""

    def test_provider_survives_short_term_init_failure(self, tmp_path):
        """ShortTermMemory 初始化失败时，provider 仍可创建，short_term 为 None。"""
        from unittest.mock import patch

        from memory.provider import BrixMemoryProvider

        with patch(
            "memory.provider.ShortTermMemory",
            side_effect=OSError("Permission denied"),
        ):
            provider = BrixMemoryProvider(data_dir=tmp_path)

        # provider 创建成功
        assert provider is not None
        # short_term 降级为 None
        assert provider.short_term is None
        # 其他组件不受影响
        assert provider.long_term is not None
        assert provider.searcher is not None

    def test_provider_survives_long_term_init_failure(self, tmp_path):
        """LongTermMemory 初始化失败时，provider 仍可创建，long_term 为 None。"""
        from unittest.mock import patch

        from memory.provider import BrixMemoryProvider

        with patch(
            "memory.provider.LongTermMemory",
            side_effect=OSError("Disk full"),
        ):
            provider = BrixMemoryProvider(data_dir=tmp_path)

        assert provider is not None
        assert provider.long_term is None
        # short_term 正常
        assert provider.short_term is not None
        # searcher 也正常创建（内部持有 None 的 long_term）
        assert provider.searcher is not None

    def test_provider_survives_searcher_init_failure(self, tmp_path):
        """KeywordMemorySearcher 初始化失败时，provider 仍可创建，searcher 为 None。"""
        from unittest.mock import patch

        from memory.provider import BrixMemoryProvider

        with patch(
            "memory.provider.KeywordMemorySearcher",
            side_effect=OSError("I/O error"),
        ):
            provider = BrixMemoryProvider(data_dir=tmp_path)

        assert provider is not None
        assert provider.searcher is None
        # short_term 和 long_term 正常
        assert provider.short_term is not None
        assert provider.long_term is not None

    def test_provider_survives_all_memory_components_failure(self, tmp_path):
        """所有记忆组件均初始化失败时，provider 仍可创建。"""
        from unittest.mock import patch

        from memory.provider import BrixMemoryProvider

        with patch(
            "memory.provider.ShortTermMemory",
            side_effect=OSError("err1"),
        ), patch(
            "memory.provider.LongTermMemory",
            side_effect=OSError("err2"),
        ), patch(
            "memory.provider.KeywordMemorySearcher",
            side_effect=OSError("err3"),
        ):
            provider = BrixMemoryProvider(data_dir=tmp_path)

        assert provider is not None
        assert provider.short_term is None
        assert provider.long_term is None
        assert provider.searcher is None

    def test_provider_core_functions_work_with_degraded_memory(self, tmp_path):
        """记忆组件降级后，provider 核心功能（session、soul 等）不受影响。"""
        from unittest.mock import patch

        from memory.provider import BrixMemoryProvider

        with patch(
            "memory.provider.ShortTermMemory",
            side_effect=OSError("Permission denied"),
        ), patch(
            "memory.provider.LongTermMemory",
            side_effect=OSError("Permission denied"),
        ), patch(
            "memory.provider.KeywordMemorySearcher",
            side_effect=OSError("Permission denied"),
        ):
            provider = BrixMemoryProvider(data_dir=tmp_path)

        # session 操作正常
        sid = provider.create_session()
        assert sid is not None
        provider.add_message("user", "hello")
        provider.save_session()
        messages = provider.load_session(sid)
        assert len(messages) == 1
        assert messages[0]["content"] == "hello"

        # get_context_messages 正常（不依赖记忆组件）
        ctx = provider.get_context_messages("system prompt")
        assert len(ctx) >= 1
