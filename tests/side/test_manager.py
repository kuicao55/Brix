"""SideTaskManager 测试。"""

from __future__ import annotations

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
