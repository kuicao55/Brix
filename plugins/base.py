"""插件基类定义。"""

from abc import ABC, abstractmethod


class Plugin(ABC):
    """插件基类。

    所有插件继承此类，实现 name 属性和可选的生命周期方法。
    插件只做逻辑，不做 UI 渲染——UI 由 CLI 层负责。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """插件名称，用于注册和查找。"""
        ...

    async def on_activate(self) -> None:
        """插件激活时调用。"""

    async def on_deactivate(self) -> None:
        """插件停用时调用。"""
