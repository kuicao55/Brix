"""SideTask 抽象基类 + SideTaskContext 数据类。

每个 side task 实现一个后台/辅助任务（如记忆管理、日程提醒等），
由 SideTaskManager 统一调度。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class SideTaskContext:
    """side task 执行时的上下文信息。"""

    llm_client: Any
    side_model: str
    config: dict
    memory: Any
    session_messages: list
    user_input: str
    hooks: Any


class SideTask(ABC):
    """side task 抽象基类。

    子类必须实现:
    - ``name`` 属性: 唯一标识符，对应 config 中的 key
    - ``execute()`` 方法: 执行任务逻辑
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """唯一标识符，映射到 config.side.tasks.{name}。"""
        ...

    def is_enabled(self, config: dict) -> bool:
        """检查 config.side.tasks.{name}.enabled 是否为 True，默认 False。"""
        try:
            return bool(config["side"]["tasks"][self.name]["enabled"])
        except (KeyError, TypeError):
            return False

    @abstractmethod
    async def execute(self, ctx: SideTaskContext) -> Any:
        """执行任务，返回任意结果。"""
        ...
