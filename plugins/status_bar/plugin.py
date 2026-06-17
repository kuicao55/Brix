"""状态栏插件：Side 任务状态跟踪（纯逻辑，无 UI）。"""

from __future__ import annotations

import threading

from plugins.base import Plugin
from plugins.status_bar import StatusBarState, TaskState, TaskStatus


class StatusBarPlugin(Plugin):
    """跟踪 Side 任务的运行状态。

    只做状态管理，不做任何渲染。CLI 层通过 get_status() 读取状态并渲染。
    """

    def __init__(self, side_model: str = "") -> None:
        self._side_model = side_model
        self._tasks: dict[str, TaskState] = {}
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "status_bar"

    def on_task_start(self, task_name: str) -> None:
        """标记任务开始。由 SideTaskManager 回调触发。"""
        with self._lock:
            self._tasks[task_name] = TaskState(
                name=task_name,
                status=TaskStatus.RUNNING,
            )

    def on_task_end(self, task_name: str, status: str, elapsed: float = 0.0) -> None:
        """标记任务结束。由 SideTaskManager 回调触发。

        Args:
            task_name: 任务名称
            status: "completed" 或 "error"
            elapsed: 耗时（秒）
        """
        task_status = TaskStatus.ERROR if status == "error" else TaskStatus.COMPLETED
        with self._lock:
            self._tasks[task_name] = TaskState(
                name=task_name,
                status=task_status,
                elapsed_seconds=elapsed,
            )

    def get_status(self) -> StatusBarState:
        """返回当前状态快照。"""
        with self._lock:
            return StatusBarState(
                side_model=self._side_model,
                tasks=list(self._tasks.values()),
            )

    def reset(self) -> None:
        """清空所有任务状态。"""
        with self._lock:
            self._tasks.clear()
