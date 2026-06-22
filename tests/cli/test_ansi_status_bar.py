"""ANSI Scroll Region 状态栏测试。"""
from __future__ import annotations

from unittest.mock import call, patch

from cli.ansi_status_bar import paint_status_bar, setup_scroll_region, teardown_scroll_region
from cli.status_bar import StatusBarRenderer
from plugins.status_bar.plugin import StatusBarPlugin


def _make_renderer(plugin: StatusBarPlugin | None = None) -> StatusBarRenderer:
    """创建测试用 renderer。"""
    if plugin is None:
        plugin = StatusBarPlugin(side_model="test-model")
    return StatusBarRenderer(plugin)


def _collect_written(mock_os_write) -> str:
    """从 os.write mock 收集所有写入的字节并解码。"""
    return b"".join(
        c.args[1] for c in mock_os_write.call_args_list
    ).decode("utf-8")


@patch("cli.ansi_status_bar.os.write")
@patch("shutil.get_terminal_size", return_value=(40, 120))
def test_setup_scroll_region(mock_size, mock_write):
    """setup_scroll_region 写入 DECSTBM 序列。"""
    setup_scroll_region()
    written = _collect_written(mock_write)
    assert "\033[1;39r" in written  # rows=40, 40-1=39
    assert "\033[39;1H" in written


@patch("cli.ansi_status_bar.os.write")
@patch("shutil.get_terminal_size", return_value=(40, 120))
def test_teardown_scroll_region(mock_size, mock_write):
    """teardown_scroll_region 恢复全屏滚动区域。"""
    teardown_scroll_region()
    written = _collect_written(mock_write)
    assert "\033[1;40r" in written
    assert "\033[40;1H" in written
    assert "\033[2K" in written


@patch("cli.ansi_status_bar.os.write")
@patch("shutil.get_terminal_size", return_value=(40, 120))
def test_paint_status_bar(mock_size, mock_write):
    """paint_status_bar 写入 DECSC + 移动 + 内容 + DECRC。"""
    renderer = _make_renderer()
    paint_status_bar(renderer)
    written = _collect_written(mock_write)
    assert "\0337" in written  # DECSC
    assert "\033[40;1H" in written  # 移到最后一行
    assert "\033[2K" in written  # 清行
    assert "test-model" in written  # 内容
    assert "\0338" in written  # DECRC


@patch("cli.ansi_status_bar.os.write")
@patch("shutil.get_terminal_size", return_value=(40, 80))
def test_paint_status_bar_truncates(mock_size, mock_write):
    """超长内容截断到终端宽度。"""
    plugin = StatusBarPlugin(side_model="x" * 200)
    renderer = _make_renderer(plugin)
    paint_status_bar(renderer)
    written = _collect_written(mock_write)
    start = written.index("\0337")
    end = written.index("\0338")
    content = written[start + 2 : end]
    assert "\u2026" in content


@patch("cli.ansi_status_bar.os.write")
@patch("shutil.get_terminal_size", return_value=(2, 80))
def test_setup_scroll_region_too_small(mock_size, mock_write):
    """终端太小时不设置滚动区域。"""
    setup_scroll_region()
    mock_write.assert_not_called()
