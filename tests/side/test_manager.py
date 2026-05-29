"""SideTaskManager 测试。"""

from __future__ import annotations

import logging

import pytest
from unittest.mock import AsyncMock, MagicMock

from side.base import SideTask, SideTaskContext
from side.manager import SideTaskManager, _sanitize_interval


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
# 12. test_should_run_pref_detection
# ------------------------------------------------------------------

def test_should_run_pref_detection(manager):
    """should_run_pref_detection 基于间隔判断。"""
    config = {"side": {"tasks": {"pref_detection": {"interval": 3}}}}
    manager.configure(config=config, llm_client=None, memory=None)

    # 0 条消息时不触发
    assert manager.should_run_pref_detection() is False

    # 1, 2 条时不触发
    manager.on_user_message()
    assert manager.should_run_pref_detection() is False
    manager.on_user_message()
    assert manager.should_run_pref_detection() is False

    # 3 条时触发
    manager.on_user_message()
    assert manager.should_run_pref_detection() is True

    # 6 条时触发
    manager.on_user_message()
    manager.on_user_message()
    manager.on_user_message()
    assert manager.should_run_pref_detection() is True


# ------------------------------------------------------------------
# Fix 1: interval 校验 — 防止 ZeroDivisionError / TypeError
# ------------------------------------------------------------------


class TestPrefDetectionIntervalSanitization:
    """should_run_pref_detection 必须处理非法 interval 值。"""

    def test_interval_zero_defaults_to_5(self, manager):
        """interval=0 会 ZeroDivisionError，必须回退到默认值 5。"""
        config = {"side": {"tasks": {"pref_detection": {"interval": 0}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        # 不应抛异常
        for _ in range(5):
            manager.on_user_message()
        assert manager.should_run_pref_detection() is True

    def test_interval_negative_defaults_to_5(self, manager):
        """interval=-3 语义无效，必须回退到默认值 5。"""
        config = {"side": {"tasks": {"pref_detection": {"interval": -3}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        for _ in range(5):
            manager.on_user_message()
        assert manager.should_run_pref_detection() is True

    def test_interval_string_defaults_to_5(self, manager):
        """interval="abc" 会 TypeError，必须回退到默认值 5。"""
        config = {"side": {"tasks": {"pref_detection": {"interval": "abc"}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        for _ in range(5):
            manager.on_user_message()
        assert manager.should_run_pref_detection() is True

    def test_interval_none_defaults_to_5(self, manager):
        """interval=None 会 TypeError，必须回退到默认值 5。"""
        config = {"side": {"tasks": {"pref_detection": {"interval": None}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        for _ in range(5):
            manager.on_user_message()
        assert manager.should_run_pref_detection() is True

    def test_interval_float_is_coerced(self, manager):
        """interval=3.5 应被转为 int(3)，基于转换后的值判断。"""
        config = {"side": {"tasks": {"pref_detection": {"interval": 3.5}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        for _ in range(3):
            manager.on_user_message()
        assert manager.should_run_pref_detection() is True


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


# ------------------------------------------------------------------
# Fix 3: interval 布尔值 — bool 是 int 子类，True 会变成 interval=1
# ------------------------------------------------------------------


class TestPrefDetectionIntervalBool:
    """_sanitize_interval 必须拒绝布尔值，防止 interval: true 变成每轮触发。"""

    def test_interval_true_defaults_to_5(self, manager):
        """interval=True 会变成 1（每轮触发），必须回退到默认值 5。"""
        config = {"side": {"tasks": {"pref_detection": {"interval": True}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        # interval 应为 5，所以第 1-4 条消息不触发
        for _ in range(4):
            manager.on_user_message()
        assert manager.should_run_pref_detection() is False
        # 第 5 条触发
        manager.on_user_message()
        assert manager.should_run_pref_detection() is True

    def test_interval_false_defaults_to_5(self, manager):
        """interval=False 会变成 0（ZeroDivisionError），必须回退到默认值 5。"""
        config = {"side": {"tasks": {"pref_detection": {"interval": False}}}}
        manager.configure(config=config, llm_client=None, memory=None)
        for _ in range(5):
            manager.on_user_message()
        assert manager.should_run_pref_detection() is True

    def test_sanitize_interval_true_warns(self, caplog):
        """_sanitize_interval(True) 应发出警告并返回默认值。"""
        with caplog.at_level(logging.WARNING, logger="side.manager"):
            result = _sanitize_interval(True)
        assert result == 5
        assert any("bool" in r.message.lower() or "true" in r.message.lower()
                    for r in caplog.records)

    def test_sanitize_interval_false_warns(self, caplog):
        """_sanitize_interval(False) 应发出警告并返回默认值。"""
        with caplog.at_level(logging.WARNING, logger="side.manager"):
            result = _sanitize_interval(False)
        assert result == 5
        assert any("bool" in r.message.lower() or "false" in r.message.lower()
                    for r in caplog.records)


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
    """side.tasks.ALL_TASKS 应可导入，包含所有 6 个 task。"""
    from side.tasks import ALL_TASKS

    assert isinstance(ALL_TASKS, list)
    assert len(ALL_TASKS) == 6
