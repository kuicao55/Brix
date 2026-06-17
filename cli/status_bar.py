"""状态栏渲染：通过 prompt_toolkit 的 bottom_toolbar 固定在输入行下方。

参考 Claude Code 的 PromptInputFooter 架构——状态栏是 prompt 的一部分，
不是独立的 overlay。prompt_toolkit 的 bottom_toolbar 天然支持这个位置。

streaming 期间 prompt 不活跃，toolbar 不可见，因此在 _process_streaming
开始前打印一行静态状态行作为补充。
"""

from __future__ import annotations

import shutil

from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.text import Text

from plugins.status_bar import TaskStatus
from plugins.status_bar.plugin import StatusBarPlugin

_BRAILLE_FRAMES = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]

# 状态栏最大宽度（超出截断）
_MAX_BAR_WIDTH = 120


def _trunc(text: str, max_len: int) -> str:
    """截断文本到 max_len，超出加省略号。"""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


class StatusBarRenderer:
    """构建状态栏内容，供 prompt_toolkit 的 bottom_toolbar 使用。

    同时支持 get_toolbar_text() 用于 streaming 期间打印静态状态行。
    """

    def __init__(self, plugin: StatusBarPlugin) -> None:
        self._plugin = plugin
        self._frame_idx = 0

    def get_toolbar(self) -> list[tuple[str, str]]:
        """返回 prompt_toolkit 格式的 toolbar 内容。

        格式: list of (style_string, text) tuples
        prompt_toolkit 会在每次渲染 prompt 时调用此方法。
        """
        status = self._plugin.get_status()
        parts: list[tuple[str, str]] = []

        # 模型名
        model = status.side_model or "side"
        parts.append(("class:status-bar.model", " {} ".format(model)))

        running = status.running_tasks
        completed = status.completed_tasks
        error_tasks = status.error_tasks

        if running:
            frame = _BRAILLE_FRAMES[self._frame_idx % len(_BRAILLE_FRAMES)]
            self._frame_idx += 1
            for t in running:
                parts.append(("class:status-bar.running", "{} {}  ".format(frame, t.name)))
        elif not completed and not error_tasks:
            parts.append(("class:status-bar.idle", "idle"))

        # 已完成任务
        for t in completed:
            elapsed = " {:.1f}s".format(t.elapsed_seconds) if t.elapsed_seconds > 0 else ""
            parts.append(("class:status-bar.completed", "\u2713 {}{}  ".format(t.name, elapsed)))

        # 出错任务
        for t in error_tasks:
            parts.append(("class:status-bar.error", "\u2717 {}  ".format(t.name)))

        return parts

    def get_toolbar_text(self) -> str:
        """返回纯文本状态行，用于 streaming 期间在 Rich 输出前打印。

        格式：model | task1 task2 | completed | errors
        超出终端宽度截断，保证单行。
        """
        status = self._plugin.get_status()
        parts: list[str] = []

        model = status.side_model or "side"
        parts.append(model)

        running = status.running_tasks
        completed = status.completed_tasks
        error_tasks = status.error_tasks

        if running:
            for t in running:
                frame = _BRAILLE_FRAMES[self._frame_idx % len(_BRAILLE_FRAMES)]
                self._frame_idx += 1
                parts.append("{} {}".format(frame, t.name))
        elif not completed and not error_tasks:
            parts.append("idle")

        for t in completed:
            elapsed = " {:.1f}s".format(t.elapsed_seconds) if t.elapsed_seconds > 0 else ""
            parts.append("\u2713 {}{}".format(t.name, elapsed))

        for t in error_tasks:
            parts.append("\u2717 {}".format(t.name))

        text = " | ".join(parts)
        # 截断到终端宽度
        try:
            width = shutil.get_terminal_size().columns
        except Exception:
            width = _MAX_BAR_WIDTH
        return _trunc(text, min(width, _MAX_BAR_WIDTH))
