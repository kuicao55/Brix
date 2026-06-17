"""插件层：注册表 + 基类。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from plugins.base import Plugin

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PluginRegistry:
    """插件注册表，管理插件的注册和生命周期。"""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        """注册插件。同名插件会被覆盖。"""
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> Plugin | None:
        """按名称获取插件。"""
        return self._plugins.get(name)

    async def activate_all(self) -> None:
        """激活所有已注册插件。单个插件失败不影响其他。"""
        for name, plugin in self._plugins.items():
            try:
                await plugin.on_activate()
            except Exception:
                logger.warning("插件 '%s' 激活失败", name, exc_info=True)

    async def deactivate_all(self) -> None:
        """停用所有已注册插件。单个插件失败不影响其他。"""
        for name, plugin in self._plugins.items():
            try:
                await plugin.on_deactivate()
            except Exception:
                logger.warning("插件 '%s' 停用失败", name, exc_info=True)

    @property
    def plugins(self) -> list[Plugin]:
        """返回所有已注册插件列表。"""
        return list(self._plugins.values())
