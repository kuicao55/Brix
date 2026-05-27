"""SideTask 抽象基类 + SideTaskContext 数据类。

每个 side task 实现一个后台/辅助任务（如记忆管理、日程提醒等），
由 SideTaskManager 统一调度。
"""

from __future__ import annotations

import copy
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

logger = logging.getLogger(__name__)


def _freeze(obj: Any) -> Any:
    """递归冻结：dict→MappingProxyType，list/tuple 中的 dict 也一并冻结。

    非容器类型原样返回。
    """
    if isinstance(obj, dict):
        return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_freeze(item) for item in obj)
    if isinstance(obj, tuple):
        return tuple(_freeze(item) for item in obj)
    return obj


@dataclass(frozen=True)
class SideTaskContext:
    """side task 执行时的上下文信息（只读）。

    - ``config`` 以 MappingProxyType 存储，防止侧任务意外修改全局配置。
    - ``session_messages`` 以 tuple 存储，防御性拷贝，防止原地修改。
    """

    llm_client: Any
    side_model: str
    config: MappingProxyType  # 只读字典
    memory: Any
    session_messages: tuple  # 只读列表（tuple 拷贝）
    user_input: str
    hooks: Any

    def __init__(
        self,
        llm_client: Any,
        side_model: str,
        config: dict,
        memory: Any,
        session_messages: list,
        user_input: str,
        hooks: Any,
    ) -> None:
        object.__setattr__(self, "llm_client", llm_client)
        object.__setattr__(self, "side_model", side_model)
        # 深拷贝 + 递归冻结：嵌套 dict 全部转为 MappingProxyType
        object.__setattr__(self, "config", _freeze(copy.deepcopy(config)))
        object.__setattr__(self, "memory", memory)
        # 深拷贝 + 递归冻结：每条消息 dict 转为 MappingProxyType
        object.__setattr__(self, "session_messages", _freeze(copy.deepcopy(session_messages)))
        object.__setattr__(self, "user_input", user_input)
        object.__setattr__(self, "hooks", hooks)


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
        """检查 config.side.tasks.{name}.enabled 是否严格为 True。

        仅接受 ``True``（bool 类型）作为启用条件。
        其他所有值（字符串、整数、None 等）均视为 disabled，
        并在遇到非布尔类型时记录 warning 以便排查配置错误。
        """
        try:
            value = config["side"]["tasks"][self.name]["enabled"]
        except (KeyError, TypeError):
            return False
        if isinstance(value, bool):
            return value
        # 非布尔类型：拒绝并警告（排查配置错误）
        logger.warning(
            "side task '%s' 的 enabled=%r 不是严格布尔值 (type=%s)，视为 disabled",
            self.name,
            value,
            type(value).__name__,
        )
        return False

    @abstractmethod
    async def execute(self, ctx: SideTaskContext) -> Any:
        """执行任务，返回任意结果。"""
        ...
