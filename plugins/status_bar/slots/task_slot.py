"""Side 任务状态 StatusSlot：显示 running / completed / error 任务。"""

from __future__ import annotations

import itertools

from plugins.status_bar import StatusBarState, StyledStatusSlot

_BRAILLE_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class TaskSlot(StyledStatusSlot):
    """在状态栏显示 side task 的运行状态。"""

    def __init__(self) -> None:
        self._frame_iter = itertools.cycle(_BRAILLE_FRAMES)

    @property
    def name(self) -> str:
        return "task"

    def get_text(self, state: StatusBarState) -> str:
        parts: list[str] = []
        running = state.running_tasks
        completed = state.completed_tasks
        error_tasks = state.error_tasks

        if running:
            for t in running:
                frame = next(self._frame_iter)
                parts.append("{} {}".format(frame, t.name))
        elif not completed and not error_tasks:
            parts.append("idle")

        for t in completed:
            elapsed = " {:.1f}s".format(t.elapsed_seconds) if t.elapsed_seconds > 0 else ""
            parts.append("✓ {}{}".format(t.name, elapsed))

        for t in error_tasks:
            parts.append("✗ {}".format(t.name))

        return "  ".join(parts)

    def get_parts(self, state: StatusBarState) -> list[tuple[str, str]]:
        parts: list[tuple[str, str]] = []
        running = state.running_tasks
        completed = state.completed_tasks
        error_tasks = state.error_tasks

        if running:
            frame = next(self._frame_iter)
            for t in running:
                parts.append(("class:status-bar.running", "{} {}  ".format(frame, t.name)))
        elif not completed and not error_tasks:
            parts.append(("class:status-bar.idle", "idle"))

        for t in completed:
            elapsed = " {:.1f}s".format(t.elapsed_seconds) if t.elapsed_seconds > 0 else ""
            parts.append(("class:status-bar.completed", "✓ {}{}  ".format(t.name, elapsed)))

        for t in error_tasks:
            parts.append(("class:status-bar.error", "✗ {}  ".format(t.name)))

        return parts
