"""状态栏插件：Side 任务状态跟踪 + slot 注册中心（纯逻辑，无 UI）。"""

from __future__ import annotations

import threading
from collections.abc import Callable

from plugins.base import Plugin
from plugins.status_bar import StatusBarState, StatusSlot, TaskState, TaskStatus


class StatusBarPlugin(Plugin):
    """跟踪 Side 任务的运行状态。

    只做状态管理，不做任何渲染。CLI 层通过 get_status() 读取状态并渲染。
    支持 on_change 回调：状态变化时通知 CLI 层重绘状态栏。
    """

    def __init__(self, side_model: str = "") -> None:
        self._side_model = side_model
        self._tasks: dict[str, TaskState] = {}
        self._lock = threading.Lock()
        self._on_change: Callable[[], None] | None = None
        self._slots: list[StatusSlot] = []

    def set_on_change(self, callback: Callable[[], None] | None) -> None:
        """注册状态变化回调（用于 CLI 层重绘 ANSI 状态栏）。"""
        self._on_change = callback

    def register_slot(self, slot: StatusSlot) -> None:
        """注册一个状态栏显示区段。同名 slot 会被覆盖。"""
        # 移除同名旧 slot
        self._slots = [s for s in self._slots if s.name != slot.name]
        self._slots.append(slot)

    def get_slots(self) -> list[StatusSlot]:
        """返回所有已注册的 slot。"""
        return list(self._slots)

    def _fire_on_change(self) -> None:
        """触发状态变化回调。在锁外调用，避免死锁。"""
        cb = self._on_change
        if cb is not None:
            try:
                cb()
            except Exception:
                pass

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
        self._fire_on_change()

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
        self._fire_on_change()

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
        self._fire_on_change()
