"""Tests for CLI modules: display, theme, spinner, stream_renderer.

TDD: These tests are written BEFORE the implementation.
Step 2 (RED): new tests should fail with ModuleNotFoundError.
Step 4 (GREEN): all should pass after implementation.
"""

import io
import pytest

from cli.display import format_response


# ------------------------------------------------------------------
# Existing display tests (passthrough — unchanged)
# ------------------------------------------------------------------

def test_format_response_plain():
    result = format_response("Hello world")
    assert "Hello world" in result


def test_format_response_code_block():
    result = format_response("Here is code:\n```python\nprint('hi')\n```")
    assert "print" in result


# ------------------------------------------------------------------
# Theme tests (Task 3)
# ------------------------------------------------------------------

def test_theme_has_required_styles():
    """BRIX_THEME should define all required style keys."""
    from rich.theme import Theme
    from cli.theme import BRIX_THEME

    assert isinstance(BRIX_THEME, Theme)
    for key in ["markdown.h1", "markdown.code_block", "tool.name", "spinner.active"]:
        style = BRIX_THEME.styles.get(key)
        assert style is not None, "Missing theme style: {}".format(key)


def test_theme_is_rich_theme_instance():
    """BRIX_THEME must be a Rich Theme instance."""
    from rich.theme import Theme
    from cli.theme import BRIX_THEME
    assert isinstance(BRIX_THEME, Theme)


def test_theme_markdown_styles_defined():
    """All markdown.* styles should be present in the theme."""
    from cli.theme import BRIX_THEME
    required = [
        "markdown.h1", "markdown.h2", "markdown.h3",
        "markdown.code", "markdown.code_block",
        "markdown.link", "markdown.em", "markdown.strong",
        "markdown.blockquote",
    ]
    for key in required:
        assert BRIX_THEME.styles.get(key) is not None, "Missing: {}".format(key)


def test_theme_tool_styles_defined():
    """tool.border, tool.name, tool.success, tool.error should exist."""
    from cli.theme import BRIX_THEME
    for key in ["tool.border", "tool.name", "tool.success", "tool.error"]:
        assert BRIX_THEME.styles.get(key) is not None, "Missing: {}".format(key)


def test_theme_spinner_styles_defined():
    """spinner.active, spinner.done, spinner.failed should exist."""
    from cli.theme import BRIX_THEME
    for key in ["spinner.active", "spinner.done", "spinner.failed"]:
        assert BRIX_THEME.styles.get(key) is not None, "Missing: {}".format(key)


# ------------------------------------------------------------------
# Spinner tests (Task 3)
# ------------------------------------------------------------------

def test_spinner_lifecycle():
    """Spinner should start, update, and finish without error."""
    from rich.console import Console
    from cli.spinner import Spinner

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)

    spinner = Spinner(console, label="Testing...")
    spinner.start()
    spinner.update_label("Still testing...")
    spinner.finish("Done")
    # Should not raise


def test_spinner_fail_lifecycle():
    """Spinner should support fail() in addition to finish()."""
    from rich.console import Console
    from cli.spinner import Spinner

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)

    spinner = Spinner(console, label="Working...")
    spinner.start()
    spinner.fail("Oops")
    # Should not raise


def test_spinner_default_label():
    """Spinner should default to 'Thinking...' label."""
    from rich.console import Console
    from cli.spinner import Spinner

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    spinner = Spinner(console)
    assert spinner.label == "Thinking..."


def test_spinner_frames_exist():
    """Spinner module should define BRAILLE_FRAMES."""
    from cli.spinner import BRAILLE_FRAMES
    assert isinstance(BRAILLE_FRAMES, list)
    assert len(BRAILLE_FRAMES) > 0


# ------------------------------------------------------------------
# StreamRenderer tests (Task 3)
# ------------------------------------------------------------------

def test_stream_renderer_safe_boundary():
    """StreamRenderer should only render at safe Markdown boundaries."""
    from rich.console import Console
    from cli.stream_renderer import StreamRenderer

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    renderer = StreamRenderer(console)

    # Push incomplete code fence — should NOT render yet
    renderer.push_delta("```python\nprint('hello')")
    assert renderer.rendered == ""  # Not rendered yet — fence not closed

    # Close the fence — NOW should render
    renderer.push_delta("\n```\n")
    assert "```python" in renderer.rendered
    assert "```" in renderer.rendered


def test_stream_renderer_flush():
    """flush() should render all remaining buffered content."""
    from rich.console import Console
    from cli.stream_renderer import StreamRenderer

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    renderer = StreamRenderer(console)

    renderer.push_delta("Hello world")
    assert renderer.rendered == ""  # No safe boundary yet

    renderer.flush()
    assert "Hello world" in renderer.rendered


def test_stream_renderer_blank_line_boundary():
    """A blank line is a safe boundary — content before it renders."""
    from rich.console import Console
    from cli.stream_renderer import StreamRenderer

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    renderer = StreamRenderer(console)

    renderer.push_delta("First paragraph.\n\n")
    assert "First paragraph" in renderer.rendered


def test_stream_renderer_no_boundary_accumulates():
    """Content with no safe boundary stays in pending, not rendered."""
    from rich.console import Console
    from cli.stream_renderer import StreamRenderer

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    renderer = StreamRenderer(console)

    renderer.push_delta("Hello ")
    assert renderer.rendered == ""
    assert renderer.pending == "Hello "


def test_stream_renderer_closed_fence_is_safe():
    """A fully closed code fence is a safe rendering boundary."""
    from rich.console import Console
    from cli.stream_renderer import StreamRenderer

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    renderer = StreamRenderer(console)

    renderer.push_delta("Before.\n\n```python\ncode\n```\n")
    assert "Before" in renderer.rendered
    assert "```python" in renderer.rendered
