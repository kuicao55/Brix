"""状态栏插件：状态模型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
