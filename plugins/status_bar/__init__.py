"""状态栏插件：状态模型 + Protocol 定义。

两个 Protocol 构成显示层的可插拔接口：
- StatusSlot：状态栏中的一个显示区段（可注册多个）
- StatusBarRendererProtocol：状态栏渲染器（可替换实现）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class TaskStatus(Enum):
    """Side 任务状态。"""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class TaskState:
    """单个 Side 任务的状态快照。"""

    name: str
    status: TaskStatus = TaskStatus.IDLE
    elapsed_seconds: float = 0.0


@dataclass
class StatusBarState:
    """状态栏整体状态快照。"""

    side_model: str = ""
    tasks: list[TaskState] = field(default_factory=list)

    @property
    def running_tasks(self) -> list[TaskState]:
        """正在运行的任务。"""
        return [t for t in self.tasks if t.status == TaskStatus.RUNNING]

    @property
    def completed_tasks(self) -> list[TaskState]:
        """已完成的任务。"""
        return [t for t in self.tasks if t.status == TaskStatus.COMPLETED]

    @property
    def error_tasks(self) -> list[TaskState]:
        """出错的任务。"""
        return [t for t in self.tasks if t.status == TaskStatus.ERROR]


# ---------------------------------------------------------------------------
# Protocol 定义
# ---------------------------------------------------------------------------


@runtime_checkable
class StatusSlot(Protocol):
    """状态栏中的一个显示区段。

    每个 slot 负责状态栏的一段内容（如模型名、task 状态、token 用量等）。
    渲染器遍历所有 slot 拼接最终输出。

    实现者只需提供 name + get_text。如需富样式，可额外实现 get_parts。
    """

    @property
    def name(self) -> str:
        """区段名称，用于注册和查找。"""
        ...

    def get_text(self, state: StatusBarState) -> str:
        """根据当前状态返回本区段的纯文本内容。返回空字符串表示不显示。"""
        ...


@runtime_checkable
class StyledStatusSlot(StatusSlot, Protocol):
    """支持 prompt_toolkit 富样式的 StatusSlot。

    渲染器优先调用 get_parts()；未实现时回退到 get_text()。
    """

    def get_parts(self, state: StatusBarState) -> list[tuple[str, str]]:
        """返回 prompt_toolkit 格式的内容（style, text 元组列表）。"""
        ...


@runtime_checkable
class StatusBarRendererProtocol(Protocol):
    """状态栏渲染器接口。

    渲染器负责聚合所有 slot 的输出，生成最终的状态栏内容。
    不同的渲染器实现可以使用不同的渲染策略（纯文本、Rich 面板等）。
    """

    def add_slot(self, slot: StatusSlot) -> None:
        """注册一个显示区段。"""
        ...

    def get_toolbar(self) -> list[tuple[str, str]]:
        """返回 prompt_toolkit 格式的 toolbar 内容。"""
        ...

    def get_toolbar_text(self) -> str:
        """返回纯文本状态行，用于 streaming 期间打印。"""
        ...
