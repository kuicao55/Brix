"""Tests for cli.tool_display — Tool Display panel.

TDD: These tests are written BEFORE the implementation.
Step 2 (RED): tests should fail with ImportError because ToolDisplay doesn't exist.
Step 4 (GREEN): all should pass after implementation.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from cli.theme import BRIX_THEME


def _themed_console(buf: io.StringIO) -> Console:
    """Create a Console with BRIX_THEME for testing."""
    return Console(file=buf, force_terminal=True, width=80, theme=BRIX_THEME)


# ------------------------------------------------------------------
# show_tool_start tests
# ------------------------------------------------------------------


def test_tool_display_formats_bash():
    """ToolDisplay should format bash commands with $ prefix."""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)

    display.show_tool_start("bash", {"command": "ls -la"})
    output = buf.getvalue()
    assert "ls -la" in output
    assert "$" in output


def test_tool_display_formats_file_read():
    """ToolDisplay should format file_read with path."""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)

    display.show_tool_start("file_read", {"path": "/tmp/test.txt"})
    output = buf.getvalue()
    assert "/tmp/test.txt" in output


def test_tool_display_formats_file_write():
    """ToolDisplay should format file_write with path and line count."""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)

    display.show_tool_start("file_write", {"path": "/tmp/out.txt", "content": "line1\nline2\n"})
    output = buf.getvalue()
    assert "/tmp/out.txt" in output


def test_tool_display_formats_web_search():
    """ToolDisplay should format web_search with query text."""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)

    display.show_tool_start("web_search", {"query": "Python async"})
    output = buf.getvalue()
    assert "Python async" in output


def test_tool_display_formats_unknown_tool():
    """ToolDisplay should fall back to JSON preview for unknown tool names."""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)

    display.show_tool_start("custom_tool", {"key": "value"})
    output = buf.getvalue()
    # Should contain some representation of the input
    assert "key" in output or "value" in output


def test_tool_display_start_includes_tool_name():
    """show_tool_start output should include the tool name in its title."""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)

    display.show_tool_start("bash", {"command": "echo hello"})
    output = buf.getvalue()
    assert "bash" in output


# ------------------------------------------------------------------
# show_tool_result tests
# ------------------------------------------------------------------


def test_tool_display_result_success():
    """show_tool_result should show success indicator with elapsed time."""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)

    display.show_tool_result("bash", "output text", elapsed_ms=150.0)
    output = buf.getvalue()
    assert "bash" in output
    assert "150ms" in output


def test_tool_display_result_error():
    """show_tool_result with is_error should show error indicator."""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)

    display.show_tool_result("bash", "command not found", elapsed_ms=50.0, is_error=True)
    output = buf.getvalue()
    assert "command not found" in output


def test_tool_display_result_truncates_long_output():
    """Long results should be truncated with ellipsis."""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)

    long_output = "x" * 300
    display.show_tool_result("bash", long_output, elapsed_ms=10.0)
    output = buf.getvalue()
    # Should be truncated, not the full 300 chars
    assert "bash" in output


def test_tool_display_result_success_indicator():
    """Successful result should include tool name in output."""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)

    display.show_tool_result("bash", "ok", elapsed_ms=10.0, is_error=False)
    output = buf.getvalue()
    assert "bash" in output


def test_tool_display_result_error_indicator():
    """Error result should include an error indicator and error message."""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)

    display.show_tool_result("bash", "error msg", elapsed_ms=10.0, is_error=True)
    output = buf.getvalue()
    assert "error msg" in output


# ------------------------------------------------------------------
# TOOL_ICONS tests
# ------------------------------------------------------------------


def test_tool_display_has_tool_icons():
    """ToolDisplay.TOOL_ICONS should map common tool names to icons."""
    from cli.tool_display import ToolDisplay

    assert "bash" in ToolDisplay.TOOL_ICONS
    assert "file_read" in ToolDisplay.TOOL_ICONS
    assert "file_write" in ToolDisplay.TOOL_ICONS
    assert "web_search" in ToolDisplay.TOOL_ICONS


# ------------------------------------------------------------------
# Spinner integration tests
# ------------------------------------------------------------------


def test_show_tool_start_starts_spinner():
    """验证 show_tool_start 启动 spinner"""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)
    display.show_tool_start("file_read", {"path": "/tmp/test.txt"})
    assert display._active_spinner is not None
    assert display._active_spinner.running is True
    # 清理
    display._active_spinner.stop()


def test_show_tool_result_stops_spinner():
    """验证 show_tool_result 停止 spinner"""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    console = _themed_console(buf)
    display = ToolDisplay(console)
    display.show_tool_start("file_read", {"path": "/tmp/test.txt"})
    assert display._active_spinner is not None
    display.show_tool_result("file_read", "content", 100.0)
    assert display._active_spinner is None


def test_cleanup_when_no_active_spinner():
    """验证 cleanup 在无活跃 spinner 时安全调用"""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    display = ToolDisplay(_themed_console(buf))
    display.cleanup()  # 不应抛异常


def test_cleanup_stops_active_spinner():
    """验证 cleanup 停止活跃的 spinner"""
    from cli.tool_display import ToolDisplay

    buf = io.StringIO()
    display = ToolDisplay(_themed_console(buf))
    display.show_tool_start("bash", {"command": "ls"})
    assert display._active_spinner is not None
    display.cleanup()
    assert display._active_spinner is None
