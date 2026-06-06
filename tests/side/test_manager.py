"""SideTaskManager 测试。"""

from __future__ import annotations

import logging

import pytest
from unittest.mock import AsyncMock, MagicMock

from side.base import SideTask, SideTaskContext
from side.manager import SideTaskManager


class MockTask(SideTask):
    """测试用 task。"""

    def __init__(self, name: str = "mock", result: str = "ok"):
        self._name = name
        self._result = result

    @property
    def name(self) -> str:
        return self._name

    async def execute(self, ctx: SideTaskContext) -> str:
        return self._result


class FailingTask(SideTask):
    """总是失败的 task。"""

    @property
    def name(self) -> str:
        return "failing"

    async def execute(self, ctx: SideTaskContext) -> None:
        raise RuntimeError("task failed")


@pytest.fixture
def manager():
    return SideTaskManager()


@pytest.fixture
def config_enabled():
    return {
        "side": {
            "enabled": True,
            "model": "test-model",
            "tasks": {
                "mock": {"enabled": True},
                "failing": {"enabled": True},
            },
        },
    }


# ------------------------------------------------------------------
# 1. test_configure
# ------------------------------------------------------------------

def test_configure(manager, config_enabled):
    """configure 设置 config、llm_client、memory、side_model。"""
    llm_client = MagicMock()
    memory = MagicMock()
    manager.configure(config=config_enabled, llm_client=llm_client, memory=memory)
    assert manager._config == config_enabled
    assert manager._llm_client == llm_client
    assert manager._memory == memory
    assert manager._side_model == "test-model"


# ------------------------------------------------------------------
# 2. test_register
# ------------------------------------------------------------------

def test_register(manager):
    """register 注册 task。"""
    task = MockTask()
    manager.register(task)
    assert "mock" in manager._tasks


# ------------------------------------------------------------------
# 3. test_enabled_property
# ------------------------------------------------------------------

def test_enabled_property(manager, config_enabled):
    """enabled 属性从 config 读取。"""
    manager.configure(config=config_enabled, llm_client=None, memory=None)
    assert manager.enabled is True

    manager.configure(config={"side": {"enabled": False}}, llm_client=None, memory=None)
    assert manager.enabled is False


# ------------------------------------------------------------------
# 4. test_get_side_model
# ------------------------------------------------------------------

def test_get_side_model(manager, config_enabled):
    """get_side_model 返回 side 模型 ID。"""
    manager.configure(config=config_enabled, llm_client=None, memory=None)
    assert manager.get_side_model() == "test-model"


# ------------------------------------------------------------------
# 5. test_run_task
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_task(manager, config_enabled):
    """run_task 执行指定 task。"""
    manager.configure(config=config_enabled, llm_client=None, memory=None)
    manager.register(MockTask())
    result = await manager.run_task("mock", session_messages=[], user_input="hi")
    assert result == "ok"


# ------------------------------------------------------------------
# 6. test_run_task_not_found
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_task_not_found(manager, config_enabled):
    """run_task 找不到 task 时返回 None。"""
    manager.configure(config=config_enabled, llm_client=None, memory=None)
    result = await manager.run_task("nonexistent")
    assert result is None


# ------------------------------------------------------------------
# 7. test_run_task_disabled
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_task_disabled(manager):
    """run_task task 未启用时返回 None。"""
    config = {"side": {"enabled": True, "model": "m", "tasks": {"mock": {"enabled": False}}}}
    manager.configure(config=config, llm_client=None, memory=None)
    manager.register(MockTask())
    result = await manager.run_task("mock")
    assert result is None


# ------------------------------------------------------------------
# 8. test_run_task_side_disabled
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_task_side_disabled(manager):
    """run_task side 总开关关闭时返回 None。"""
    config = {"side": {"enabled": False, "model": "m", "tasks": {"mock": {"enabled": True}}}}
    manager.configure(config=config, llm_client=None, memory=None)
    manager.register(MockTask())
    result = await manager.run_task("mock")
    assert result is None


# ------------------------------------------------------------------
# 9. test_run_task_no_model
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_task_no_model(manager):
    """run_task 没有 side model 时返回 None。"""
    config = {"side": {"enabled": True, "model": "", "tasks": {"mock": {"enabled": True}}}}
    manager.configure(config=config, llm_client=None, memory=None)
    manager.register(MockTask())
    result = await manager.run_task("mock")
    assert result is None


# ------------------------------------------------------------------
# 10. test_run_task_exception
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_task_exception(manager, config_enabled):
    """run_task 异常时返回 None，不抛出。"""
    manager.configure(config=config_enabled, llm_client=None, memory=None)
    manager.register(FailingTask())
    result = await manager.run_task("failing")
    assert result is None


# ------------------------------------------------------------------
# 11. test_on_user_message
# ------------------------------------------------------------------

def test_on_user_message(manager):
    """on_user_message 递增计数器。"""
    assert manager._user_message_count == 0
    manager.on_user_message()
    assert manager._user_message_count == 1
    manager.on_user_message()
    assert manager._user_message_count == 2


# ------------------------------------------------------------------
# 11.5. test_should_run_session_title
# ------------------------------------------------------------------

def test_should_run_session_title(manager):
    """should_run_session_title 在第 1、3 条用户消息时触发。"""
    manager.configure(config={}, llm_client=None, memory=None)

    # 0 条消息时不触发
    assert manager.should_run_session_title() is False

    # 第 1 条消息触发
    manager.on_user_message()
    assert manager.should_run_session_title() is True

    # 第 2 条消息不触发
    manager.on_user_message()
    assert manager.should_run_session_title() is False

    # 第 3 条消息触发
    manager.on_user_message()
    assert manager.should_run_session_title() is True

    # 第 4 条及以后不触发
    manager.on_user_message()
    assert manager.should_run_session_title() is False
    manager.on_user_message()
    assert manager.should_run_session_title() is False


# ------------------------------------------------------------------
# Fix 2: fire_and_forget 缺少 event loop
# ------------------------------------------------------------------


class TestFireAndForgetNoLoop:
    """fire_and_forget 在没有运行中 event loop 时应安全跳过。"""

    def test_fire_and_forget_no_running_loop(self, manager, config_enabled, caplog):
        """没有 event loop 时，fire_and_forget 不抛异常，仅警告。"""
        manager.configure(config=config_enabled, llm_client=None, memory=None)
        manager.register(MockTask())
        with caplog.at_level(logging.WARNING, logger="side.manager"):
            manager.fire_and_forget("mock")
        # 不应抛 RuntimeError
        assert any("event loop" in r.message.lower() or "running" in r.message.lower()
                    for r in caplog.records if r.levelno >= logging.WARNING)


@pytest.mark.asyncio
async def test_fire_and_forget_on_result(manager, config_enabled):
    """fire_and_forget 的 on_result 回调接收 task 返回值。"""
    manager.configure(config=config_enabled, llm_client=None, memory=None)
    manager.register(MockTask(result="title-value"))
    callback = AsyncMock()

    manager.fire_and_forget("mock", on_result=callback)
    # 等待 asyncio.create_task 完成
    import asyncio
    await asyncio.sleep(0.05)

    callback.assert_awaited_once_with("title-value")


@pytest.mark.asyncio
async def test_fire_and_forget_on_result_none(manager, config_enabled):
    """task 返回 None 时不调用 on_result。"""
    manager.configure(config=config_enabled, llm_client=None, memory=None)
    manager.register(MockTask(result=None))
    callback = AsyncMock()

    manager.fire_and_forget("mock", on_result=callback)
    import asyncio
    await asyncio.sleep(0.05)

    callback.assert_not_awaited()


@pytest.mark.asyncio
async def test_fire_and_forget_on_result_exception(manager, config_enabled, caplog):
    """on_result 回调异常不影响主流程。"""
    manager.configure(config=config_enabled, llm_client=None, memory=None)
    manager.register(MockTask(result="val"))

    async def _bad_callback(val):
        raise RuntimeError("callback boom")

    manager.fire_and_forget("mock", on_result=_bad_callback)
    import asyncio
    await asyncio.sleep(0.05)

    assert any("on_result" in r.message for r in caplog.records)


# ------------------------------------------------------------------
# Fix 4: side.enabled 严格布尔检查 — 与 SideTask.is_enabled() 一致
# ------------------------------------------------------------------


class TestSideEnabledStrictBool:
    """side.enabled 必须严格检查 bool 类型，非布尔值视为 disabled。"""

    def test_enabled_string_false_is_disabled(self, manager):
        """enabled: "false" 是非空字符串 — truthiness 为 True，必须拒绝。"""
        config = {"side": {"enabled": "false", "model": "m", "tasks": {"mock": {"enabled": True}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        assert manager.enabled is False

    def test_enabled_string_zero_is_disabled(self, manager):
        """enabled: "0" 是非空字符串 — 必须拒绝。"""
        config = {"side": {"enabled": "0", "model": "m", "tasks": {"mock": {"enabled": True}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        assert manager.enabled is False

    def test_enabled_int_one_is_disabled(self, manager):
        """enabled: 1 不是严格布尔 — 必须拒绝。"""
        config = {"side": {"enabled": 1, "model": "m", "tasks": {"mock": {"enabled": True}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        assert manager.enabled is False

    def test_enabled_none_is_disabled(self, manager):
        """enabled: None — 必须拒绝。"""
        config = {"side": {"enabled": None, "model": "m", "tasks": {"mock": {"enabled": True}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        assert manager.enabled is False

    def test_enabled_bool_true_is_enabled(self, manager):
        """enabled: True 是严格布尔 — 必须通过。"""
        config = {"side": {"enabled": True, "model": "m", "tasks": {"mock": {"enabled": True}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        assert manager.enabled is True

    def test_enabled_bool_false_is_disabled(self, manager):
        """enabled: False 是严格布尔 — 正常禁用，不警告。"""
        config = {"side": {"enabled": False, "model": "m", "tasks": {"mock": {"enabled": True}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        assert manager.enabled is False

    def test_enabled_missing_key_is_disabled(self, manager):
        """缺少 enabled 键 — 必须禁用。"""
        config = {"side": {"model": "m"}}
        manager.configure(config=config, llm_client=None, memory=None)
        assert manager.enabled is False


class TestRunTaskStrictBoolGate:
    """_is_task_enabled 的全局开关必须严格布尔检查。"""

    @pytest.mark.asyncio
    async def test_string_false_blocks_task(self, manager):
        """enabled: "false" 必须阻塞 task 执行。"""
        config = {"side": {"enabled": "false", "model": "m", "tasks": {"mock": {"enabled": True}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        manager.register(MockTask())
        result = await manager.run_task("mock")
        assert result is None

    @pytest.mark.asyncio
    async def test_int_one_blocks_task(self, manager):
        """enabled: 1 必须阻塞 task 执行。"""
        config = {"side": {"enabled": 1, "model": "m", "tasks": {"mock": {"enabled": True}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        manager.register(MockTask())
        result = await manager.run_task("mock")
        assert result is None

    @pytest.mark.asyncio
    async def test_none_blocks_task(self, manager):
        """enabled: None 必须阻塞 task 执行。"""
        config = {"side": {"enabled": None, "model": "m", "tasks": {"mock": {"enabled": True}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        manager.register(MockTask())
        result = await manager.run_task("mock")
        assert result is None

    @pytest.mark.asyncio
    async def test_bool_true_allows_task(self, manager):
        """enabled: True 允许 task 执行。"""
        config = {"side": {"enabled": True, "model": "m", "tasks": {"mock": {"enabled": True}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        manager.register(MockTask())
        result = await manager.run_task("mock")
        assert result == "ok"


class TestSideEnabledNonBoolWarning:
    """非布尔值应触发 warning 日志。"""

    def test_string_false_warns(self, manager, caplog):
        """enabled: "false" 应触发 warning。"""
        config = {"side": {"enabled": "false", "model": "m"}}
        with caplog.at_level(logging.WARNING, logger="side.manager"):
            manager.configure(config=config, llm_client=None, memory=None)
            _ = manager.enabled
        assert any("布尔" in r.message for r in caplog.records if r.levelno >= logging.WARNING)

    def test_int_one_warns(self, manager, caplog):
        """enabled: 1 应触发 warning。"""
        config = {"side": {"enabled": 1, "model": "m"}}
        with caplog.at_level(logging.WARNING, logger="side.manager"):
            manager.configure(config=config, llm_client=None, memory=None)
            _ = manager.enabled
        assert any("布尔" in r.message for r in caplog.records if r.levelno >= logging.WARNING)

    def test_bool_true_no_warning(self, manager, caplog):
        """enabled: True 不应触发 warning。"""
        config = {"side": {"enabled": True, "model": "m"}}
        with caplog.at_level(logging.WARNING, logger="side.manager"):
            manager.configure(config=config, llm_client=None, memory=None)
            _ = manager.enabled
        assert not any("布尔" in r.message for r in caplog.records if r.levelno >= logging.WARNING)

    def test_bool_false_no_warning(self, manager, caplog):
        """enabled: False 不应触发 warning。"""
        config = {"side": {"enabled": False, "model": "m"}}
        with caplog.at_level(logging.WARNING, logger="side.manager"):
            manager.configure(config=config, llm_client=None, memory=None)
            _ = manager.enabled
        assert not any("布尔" in r.message for r in caplog.records if r.levelno >= logging.WARNING)


# ------------------------------------------------------------------
# Tasks 包入口
# ------------------------------------------------------------------


def test_import_all_tasks():
    """side.tasks.ALL_TASKS 应可导入，包含所有 7 个 task（pref_detection 已移除）。"""
    from side.tasks import ALL_TASKS

    assert isinstance(ALL_TASKS, list)
    assert len(ALL_TASKS) == 7
