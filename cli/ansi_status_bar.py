"""ANSI Scroll Region 状态栏。

原理与 tmux 状态栏相同：用 DECSTBM 设置终端滚动区域，
将底部 1 行排除在滚动区域之外，所有正常输出（Rich、prompt_toolkit）
被限制在滚动区域内，状态栏永远固定在最底部。

必须用 os.write(1, ...) 直写 fd 1，绕过 Rich 的 FileProxy——
FileProxy 会把非 SGR 的 ANSI 序列（DECSC/cursor/erase）静默吞掉。

参考：https://invisible-island.net/xterm/ctlseqs/ctlseqs.html#h3-Scrolling-Region
"""

from __future__ import annotations

import os

from cli.status_bar import StatusBarRenderer


def _write(raw: str) -> None:
    """直写 fd 1，绕过 sys.stdout（可能被 Rich FileProxy 劫持）。"""
    os.write(1, raw.encode("utf-8"))


def setup_scroll_region(status_lines: int = 1) -> None:
    """设置终端滚动区域，保留底部 N 行给状态栏。

    DECSTBM: \\033[{top};{bottom}r
    设置后，所有正常输出只在 top..bottom 区域内滚动。
    """
    import shutil
    rows, _ = shutil.get_terminal_size()
    if rows <= status_lines + 1:
        return
    _write("\033[1;{}r".format(rows - status_lines))
    # 光标移到滚动区域底部（状态栏上方一行）
    _write("\033[{};1H".format(rows - status_lines))


def teardown_scroll_region() -> None:
    """恢复终端默认滚动区域（全屏）。"""
    import shutil
    rows, _ = shutil.get_terminal_size()
    _write("\033[1;{}r".format(rows))
    # 清除状态栏行
    _write("\033[{};1H\033[2K".format(rows))


def paint_status_bar(renderer: StatusBarRenderer) -> None:
    """在保留区域（最后一行）绘制状态栏。

    DECSC (\\0337) 保存光标位置 → 移到最后一行 → 清行 → 写内容 → DECRC (\\0338) 恢复。
    """
    import shutil
    rows, cols = shutil.get_terminal_size()
    text = renderer.get_toolbar_text()
    if not text:
        text = " "
    # 截断到终端宽度
    if len(text) > cols:
        text = text[: cols - 1] + "\u2026"
    _write("\0337\033[{};1H\033[2K{}\0338".format(rows, text))
