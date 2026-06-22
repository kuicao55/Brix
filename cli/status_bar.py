"""状态栏渲染：通过 prompt_toolkit 的 bottom_toolbar 固定在输入行下方。

参考 Claude Code 的 PromptInputFooter 架构——状态栏是 prompt 的一部分，
不是独立的 overlay。prompt_toolkit 的 bottom_toolbar 天然支持这个位置。

streaming 期间 prompt 不活跃，toolbar 不可见，因此在 _process_streaming
开始前打印一行静态状态行作为补充。

渲染器实现 StatusBarRendererProtocol，作为纯 slot 聚合器：
所有显示内容由已注册的 StatusSlot 提供，渲染器只负责拼接和格式化。
"""

from __future__ import annotations

import shutil

from plugins.status_bar import StatusSlot, StyledStatusSlot
from plugins.status_bar.plugin import StatusBarPlugin

# 状态栏最大宽度（超出截断）
_MAX_BAR_WIDTH = 120


def _trunc(text: str, max_len: int) -> str:
    """截断文本到 max_len，超出加省略号。"""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class StatusBarRenderer:
    """纯 slot 聚合器：遍历已注册 slot 拼接状态栏内容。

    不包含任何硬编码的显示逻辑——模型名、task 状态等都由对应的
    StatusSlot 提供。替换此渲染器只需实现 StatusBarRendererProtocol。
    """

    def __init__(self, plugin: StatusBarPlugin) -> None:
        self._plugin = plugin

    def add_slot(self, slot: StatusSlot) -> None:
        """注册一个显示区段，委托给 plugin 的 slot 注册表。"""
        self._plugin.register_slot(slot)

    def get_toolbar(self) -> list[tuple[str, str]]:
        """返回 prompt_toolkit 格式的 toolbar 内容。

        遍历所有已注册 slot，StyledStatusSlot 调用 get_parts()，
        普通 StatusSlot 调用 get_text() 包装为无样式文本。
        """
        status = self._plugin.get_status()
        parts: list[tuple[str, str]] = []

        for slot in self._plugin.get_slots():
            if isinstance(slot, StyledStatusSlot):
                slot_parts = slot.get_parts(status)
                if slot_parts:
                    parts.extend(slot_parts)
            else:
                text = slot.get_text(status)
                if text:
                    parts.append(("", text))

        return parts

    def get_toolbar_text(self) -> str:
        """返回纯文本状态行，用于 streaming 期间在 Rich 输出前打印。

        遍历所有已注册 slot，取 get_text() 拼接。
        超出终端宽度截断，保证单行。
        """
        status = self._plugin.get_status()
        parts: list[str] = []

        for slot in self._plugin.get_slots():
            text_part = slot.get_text(status)
            if text_part:
                parts.append(text_part)

        text = " | ".join(parts)
        # 截断到终端宽度
        try:
            width = shutil.get_terminal_size().columns
        except Exception:
            width = _MAX_BAR_WIDTH
        return _trunc(text, min(width, _MAX_BAR_WIDTH))
