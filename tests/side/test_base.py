"""Tests for side/base.py — SideTask 抽象基类 + SideTaskContext 数据类。"""

from __future__ import annotations

import logging

import pytest
from types import MappingProxyType
from unittest.mock import MagicMock

from side.base import SideTask, SideTaskContext, _freeze


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
# test_side_task_is_enabled — 严格布尔检查
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

    # --- CQR: 边界情况，非布尔值必须视为 disabled ---

    def test_string_false_is_disabled(self):
        """enabled: "false" 是非空字符串，bool("false") == True — 必须拒绝。"""
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {"enabled": "false"}}}}
        assert task.is_enabled(config) is False

    def test_string_zero_is_disabled(self):
        """enabled: "0" 是非空字符串 — 必须拒绝。"""
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {"enabled": "0"}}}}
        assert task.is_enabled(config) is False

    def test_int_zero_is_disabled(self):
        """enabled: 0 是 falsy 但不是 bool — 必须拒绝。"""
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {"enabled": 0}}}}
        assert task.is_enabled(config) is False

    def test_none_is_disabled(self):
        """enabled: None 必须拒绝。"""
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {"enabled": None}}}}
        assert task.is_enabled(config) is False

    def test_int_one_is_disabled(self):
        """enabled: 1 不是严格布尔 — 必须拒绝。"""
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {"enabled": 1}}}}
        assert task.is_enabled(config) is False

    def test_string_true_is_disabled(self):
        """enabled: "true" 是字符串，不是布尔 — 必须拒绝。"""
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {"enabled": "true"}}}}
        assert task.is_enabled(config) is False

    def test_missing_key_is_disabled(self):
        """完全缺少 enabled 键 — 必须拒绝。"""
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {}}}}
        assert task.is_enabled(config) is False


# ------------------------------------------------------------------
# test_side_task_context — 只读性
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
        assert ctx.config["key"] == "val"
        assert ctx.session_messages[0] == {"role": "user", "content": "hi"}
        assert ctx.user_input == "hello"

    def test_config_is_readonly_mapping(self):
        """config 必须是 MappingProxyType，不允许写入。"""
        ctx = SideTaskContext(
            llm_client=MagicMock(),
            side_model="m",
            config={"a": 1},
            memory=MagicMock(),
            session_messages=[],
            user_input="",
            hooks=MagicMock(),
        )
        assert isinstance(ctx.config, MappingProxyType)
        with pytest.raises(TypeError):
            ctx.config["b"] = 2  # type: ignore[index]

    def test_session_messages_is_tuple(self):
        """session_messages 必须是 tuple 拷贝，不允许原地修改。"""
        original = [{"role": "user", "content": "hi"}]
        ctx = SideTaskContext(
            llm_client=MagicMock(),
            side_model="m",
            config={},
            memory=MagicMock(),
            session_messages=original,
            user_input="",
            hooks=MagicMock(),
        )
        assert isinstance(ctx.session_messages, tuple)
        with pytest.raises(AttributeError):
            ctx.session_messages.append({"role": "assistant", "content": "yo"})
        # 修改原始列表不影响 context
        original.append({"role": "assistant", "content": "yo"})
        assert len(ctx.session_messages) == 1

    def test_frozen_no_setattr(self):
        """SideTaskContext 应为 frozen dataclass。"""
        ctx = SideTaskContext(
            llm_client=MagicMock(),
            side_model="m",
            config={},
            memory=MagicMock(),
            session_messages=[],
            user_input="",
            hooks=MagicMock(),
        )
        with pytest.raises(AttributeError):
            ctx.user_input = "mutated"


# ------------------------------------------------------------------
# test_side_task_execute
# ------------------------------------------------------------------

class TestSideTaskContextDeepImmutability:
    """深不可变性测试：嵌套 dict/list 也必须不可变。"""

    def test_nested_config_mutation_raises(self):
        """通过 ctx.config["side"]["tasks"]["dummy"]["enabled"] 修改必须抛 TypeError。"""
        config = {"side": {"tasks": {"dummy": {"enabled": True}}}}
        ctx = SideTaskContext(
            llm_client=MagicMock(),
            side_model="m",
            config=config,
            memory=MagicMock(),
            session_messages=[],
            user_input="",
            hooks=MagicMock(),
        )
        # 顶层已经是 MappingProxyType — 确认
        assert isinstance(ctx.config, MappingProxyType)
        # 嵌套层也必须是 MappingProxyType
        assert isinstance(ctx.config["side"], MappingProxyType)
        assert isinstance(ctx.config["side"]["tasks"]["dummy"], MappingProxyType)
        # 尝试修改嵌套层 — 必须抛 TypeError
        with pytest.raises(TypeError):
            ctx.config["side"]["tasks"]["dummy"]["enabled"] = False  # type: ignore[index]

    def test_session_message_content_mutation_raises(self):
        """通过 ctx.session_messages[i]["content"] 修改必须抛 TypeError。"""
        messages = [{"role": "user", "content": "hi"}]
        ctx = SideTaskContext(
            llm_client=MagicMock(),
            side_model="m",
            config={},
            memory=MagicMock(),
            session_messages=messages,
            user_input="",
            hooks=MagicMock(),
        )
        # 消息必须是 MappingProxyType
        assert isinstance(ctx.session_messages[0], MappingProxyType)
        with pytest.raises(TypeError):
            ctx.session_messages[0]["content"] = "mutated"  # type: ignore[index]

    def test_original_config_unchanged_after_construction(self):
        """构造 SideTaskContext 后，原始 config 不受影响。"""
        config = {"side": {"tasks": {"dummy": {"enabled": True}}}}
        ctx = SideTaskContext(
            llm_client=MagicMock(),
            side_model="m",
            config=config,
            memory=MagicMock(),
            session_messages=[],
            user_input="",
            hooks=MagicMock(),
        )
        # 原始 dict 仍可正常修改（不是被冻结的同一对象）
        config["side"]["tasks"]["dummy"]["enabled"] = False
        assert config["side"]["tasks"]["dummy"]["enabled"] is False
        # ctx 中的值应仍为 True（深拷贝隔离）
        assert ctx.config["side"]["tasks"]["dummy"]["enabled"] is True

    def test_original_messages_unchanged_after_construction(self):
        """构造 SideTaskContext 后，原始 session_messages 不受影响。"""
        messages = [{"role": "user", "content": "hi"}]
        ctx = SideTaskContext(
            llm_client=MagicMock(),
            side_model="m",
            config={},
            memory=MagicMock(),
            session_messages=messages,
            user_input="",
            hooks=MagicMock(),
        )
        # 修改原始列表
        messages[0]["content"] = "mutated"
        assert messages[0]["content"] == "mutated"
        # ctx 中的值应仍为 "hi"
        assert ctx.session_messages[0]["content"] == "hi"


class TestFreezeTupleRecursion:
    """Fix 1: _freeze() 必须递归处理 tuple 内的 dict。"""

    def test_tuple_contained_dict_is_frozen(self):
        """tuple 中的 dict 应被转为 MappingProxyType。"""
        data = {"items": ({"name": "a"}, {"name": "b"})}
        frozen = _freeze(data)
        assert isinstance(frozen["items"], tuple)
        for item in frozen["items"]:
            assert isinstance(item, MappingProxyType)

    def test_tuple_contained_dict_is_immutable(self):
        """tuple 中的 dict 冻结后不可修改。"""
        data = {"items": ({"name": "a"},)}
        frozen = _freeze(data)
        with pytest.raises(TypeError):
            frozen["items"][0]["name"] = "mutated"  # type: ignore[index]

    def test_context_with_tuple_in_config(self):
        """SideTaskContext.config 中 tuple 值里的 dict 必须被冻结。"""
        config = {"tags": ({"k": "v"},)}
        ctx = SideTaskContext(
            llm_client=MagicMock(),
            side_model="m",
            config=config,
            memory=MagicMock(),
            session_messages=[],
            user_input="",
            hooks=MagicMock(),
        )
        assert isinstance(ctx.config["tags"], tuple)
        assert isinstance(ctx.config["tags"][0], MappingProxyType)
        with pytest.raises(TypeError):
            ctx.config["tags"][0]["k"] = "mutated"  # type: ignore[index]


class TestIsEnabledBooleanWarning:
    """Fix 2: enabled=False 不应产生 warning 日志。"""

    def test_enabled_false_no_warning(self, caplog):
        """enabled: False 是合法布尔值，不应触发 warning。"""
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {"enabled": False}}}}
        with caplog.at_level(logging.WARNING, logger="side.base"):
            result = task.is_enabled(config)
        assert result is False
        warning_messages = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_messages) == 0, (
            f"expected no warnings, got: {[r.message for r in warning_messages]}"
        )

    def test_enabled_true_no_warning(self, caplog):
        """enabled: True 也不应触发 warning。"""
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {"enabled": True}}}}
        with caplog.at_level(logging.WARNING, logger="side.base"):
            result = task.is_enabled(config)
        assert result is True
        warning_messages = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_messages) == 0

    def test_non_bool_value_still_warns(self, caplog):
        """enabled: 1 (int) 不是布尔值，仍应触发 warning。"""
        task = DummyTask()
        config = {"side": {"tasks": {"dummy": {"enabled": 1}}}}
        with caplog.at_level(logging.WARNING, logger="side.base"):
            result = task.is_enabled(config)
        assert result is False
        warning_messages = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_messages) == 1


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
