"""PluginRegistry 测试。"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from plugins import PluginRegistry
from plugins.base import Plugin


class _DummyPlugin(Plugin):
    def __init__(self, name: str = "dummy") -> None:
        self._name = name
        self.activated = False
        self.deactivated = False

    @property
    def name(self) -> str:
        return self._name

    async def on_activate(self) -> None:
        self.activated = True

    async def on_deactivate(self) -> None:
        self.deactivated = True


def test_register_and_get():
    """注册插件后可通过名称获取。"""
    registry = PluginRegistry()
    plugin = _DummyPlugin("test")
    registry.register(plugin)
    assert registry.get("test") is plugin


def test_get_nonexistent():
    """获取未注册的插件返回 None。"""
    registry = PluginRegistry()
    assert registry.get("nonexistent") is None


@pytest.mark.asyncio
async def test_activate_all():
    """activate_all 激活所有插件。"""
    registry = PluginRegistry()
    p1 = _DummyPlugin("a")
    p2 = _DummyPlugin("b")
    registry.register(p1)
    registry.register(p2)
    await registry.activate_all()
    assert p1.activated
    assert p2.activated


@pytest.mark.asyncio
async def test_deactivate_all():
    """deactivate_all 停用所有插件。"""
    registry = PluginRegistry()
    p1 = _DummyPlugin("a")
    p2 = _DummyPlugin("b")
    registry.register(p1)
    registry.register(p2)
    await registry.deactivate_all()
    assert p1.deactivated
    assert p2.deactivated


@pytest.mark.asyncio
async def test_activate_all_error_handling():
    """一个插件激活失败不影响其他插件。"""
    registry = PluginRegistry()

    class _FailPlugin(Plugin):
        @property
        def name(self) -> str:
            return "fail"

        async def on_activate(self) -> None:
            raise RuntimeError("boom")

    good = _DummyPlugin("good")
    registry.register(_FailPlugin())
    registry.register(good)
    await registry.activate_all()
    assert good.activated


def test_plugins_property():
    """plugins 属性返回所有已注册插件列表。"""
    registry = PluginRegistry()
    p1 = _DummyPlugin("a")
    p2 = _DummyPlugin("b")
    registry.register(p1)
    registry.register(p2)
    assert registry.plugins == [p1, p2]
