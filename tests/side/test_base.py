"""Tests for side/base.py — SideTask 抽象基类 + SideTaskContext 数据类。"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from side.base import SideTask, SideTaskContext


# ------------------------------------------------------------------
# 辅助
# ------------------------------------------------------------------

class DummyTask(SideTask):
    """用于测试的具体实现。"""

    @property
    def name(self) -> str:
        return "dummy"

    async def execute(self, ctx: SideTaskContext) -> str:
        return f"done-{ctx.user_input}"


# ------------------------------------------------------------------
# test_side_task_name
# ------------------------------------------------------------------

class TestSideTaskName:
    def test_dummy_name(self):
        task = DummyTask()
        assert task.name == "dummy"


# ------------------------------------------------------------------
# test_side_task_is_enabled_default
# ------------------------------------------------------------------

class TestSideTaskIsEnabled:
    def test_enabled_true(self):
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {"enabled": True}}}}
        assert task.is_enabled(config) is True

    def test_enabled_false(self):
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {"enabled": False}}}}
        assert task.is_enabled(config) is False

    def test_empty_config(self):
        task = DummyTask()
        assert task.is_enabled({}) is False


# ------------------------------------------------------------------
# test_side_task_context_fields
# ------------------------------------------------------------------

class TestSideTaskContext:
    def test_all_fields_accessible(self):
        llm = MagicMock()
        ctx = SideTaskContext(
            llm_client=llm,
            side_model="gemini-2.5-flash",
            config={"key": "val"},
            memory=MagicMock(),
            session_messages=[{"role": "user", "content": "hi"}],
            user_input="hello",
            hooks=MagicMock(),
        )
        assert ctx.llm_client is llm
        assert ctx.side_model == "gemini-2.5-flash"
        assert ctx.config == {"key": "val"}
        assert ctx.session_messages == [{"role": "user", "content": "hi"}]
        assert ctx.user_input == "hello"


# ------------------------------------------------------------------
# test_side_task_execute
# ------------------------------------------------------------------

class TestSideTaskExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_expected(self):
        task = DummyTask()
        ctx = SideTaskContext(
            llm_client=MagicMock(),
            side_model="test-model",
            config={},
            memory=MagicMock(),
            session_messages=[],
            user_input="world",
            hooks=MagicMock(),
        )
        result = await task.execute(ctx)
        assert result == "done-world"
