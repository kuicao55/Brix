"""Tests for CLI modules: display, theme, spinner, stream_renderer.

TDD: These tests are written BEFORE the implementation.
Step 2 (RED): new tests should fail with ModuleNotFoundError.
Step 4 (GREEN): all should pass after implementation.
"""

import io
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from cli.display import format_response


def _make_mock_memory():
    """创建标准 mock MemoryProvider，供 CLI 测试使用。"""
    mock_mem = MagicMock()
    mock_mem.get_context_messages.return_value = [
        {"role": "system", "content": "You are a helpful assistant."},
    ]
    mock_mem.build_system_prompt.return_value = "You are a helpful assistant."
    mock_mem.save_session.return_value = None
    mock_mem.add_message.return_value = None
    mock_mem.create_session.return_value = "test-session-uuid"
    mock_mem.list_sessions.return_value = []
    mock_mem.load_session.return_value = []
    mock_mem.load_sessions_index.return_value = []
    mock_mem.resume_session.return_value = []
    mock_mem.soul_exists.return_value = False
    mock_mem.user_memory_exists.return_value = False
    mock_mem.load_soul.return_value = ""
    mock_mem.load_user_memory.return_value = ""
    return mock_mem


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


def test_theme_stage_styles_defined():
    """stage.name, stage.time, stage.detail should exist in theme."""
    from cli.theme import BRIX_THEME
    for key in ["stage.name", "stage.time", "stage.detail"]:
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


def test_stream_renderer_newline_outside_fence_is_safe():
    """A newline outside a code fence should be a safe rendering boundary.

    This ensures single-paragraph responses render incrementally at each
    newline rather than waiting until flush().
    """
    from rich.console import Console
    from cli.stream_renderer import StreamRenderer

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    renderer = StreamRenderer(console)

    # Simulate streaming: text arrives with embedded newlines
    # but no blank lines (double-newlines) and no code fences.
    # Without trailing \n, no empty-line element is created by split().
    renderer.push_delta("Line one\nLine two")
    assert "Line one" in renderer.rendered, (
        "Newline outside fence should be a safe boundary"
    )


def test_stream_renderer_newline_inside_fence_not_safe():
    """Newlines inside a code fence should NOT be treated as safe boundaries.

    Content inside an open code fence must wait until the fence closes.
    """
    from rich.console import Console
    from cli.stream_renderer import StreamRenderer

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    renderer = StreamRenderer(console)

    # Push an opening fence and some code lines
    renderer.push_delta("```python\nprint('hello')\nprint('world')\n")
    # Should NOT render yet — fence is still open
    assert renderer.rendered == ""
    assert "print" in renderer.pending

    # Close the fence
    renderer.push_delta("```\n")
    assert "print('hello')" in renderer.rendered


def test_stream_renderer_marker_printed_inline():
    """StreamRenderer with marker should print it inline (end='') before Live starts."""
    from rich.console import Console
    from rich.text import Text
    from cli.stream_renderer import StreamRenderer

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    marker = Text("⏺ ", style="green")
    renderer = StreamRenderer(console, marker=marker)

    renderer.start()
    renderer.push_delta("Hello world\n")
    renderer.flush()

    output = buf.getvalue()
    # Marker and content should be in the output
    assert "⏺" in output
    assert "Hello world" in output


def test_stream_renderer_no_marker_works():
    """StreamRenderer without marker should work as before."""
    from rich.console import Console
    from cli.stream_renderer import StreamRenderer

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    renderer = StreamRenderer(console)

    renderer.start()
    renderer.push_delta("Hello\n")
    renderer.flush()

    output = buf.getvalue()
    assert "Hello" in output


# ------------------------------------------------------------------
# Spinner lifecycle fix tests (Issue 1: spinner stops on tool-only streams)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spinner_stops_on_tool_only_stream():
    """StageIndicator must finish when stream yields only tool events (no text_delta).

    Regression test: previously the spinner only stopped on first text_delta,
    so tool-only streams left the spinner running indefinitely.
    Now StageIndicator wraps Spinner; finish() must still be called.
    """
    from cli.app import BrixCLI
    from cli.stage_indicator import StageIndicator

    async def tool_only_stream():
        yield {"type": "tool_call", "name": "calculator"}
        yield {"type": "tool_result", "name": "calculator", "ms": 42}

    mock_indicator = MagicMock(spec=StageIndicator)
    mock_mem = _make_mock_memory()

    with patch("cli.app.StageIndicator", return_value=mock_indicator), \
         patch("cli.app.load_config", return_value={
             "routing": {"default_model": "test-model"},
             "memory": {"max_context_tokens": 8000},
         }), \
         patch("cli.app.create_memory_provider", return_value=mock_mem), \
         patch("cli.app.classify_intent", new_callable=AsyncMock, return_value="tool_use"), \
         patch("cli.app.evaluate_complexity", return_value="low"), \
         patch("cli.app.select_model", return_value="test-model"):

        cli = BrixCLI()
        cli._orchestrator = MagicMock()
        cli._orchestrator.run_stream = MagicMock(return_value=tool_only_stream())

        await cli._process_streaming("calculate something")

        # StageIndicator.finish() must have been called (not left running)
        mock_indicator.finish.assert_called()


@pytest.mark.asyncio
async def test_spinner_stops_on_empty_stream():
    """StageIndicator must finish when stream yields no events at all.

    Regression test: an empty stream (immediate end) previously left the
    spinner running indefinitely because no text_delta ever arrived.
    Now StageIndicator wraps Spinner; finish() must still be called.
    """
    from cli.app import BrixCLI
    from cli.stage_indicator import StageIndicator

    async def empty_stream():
        return
        yield  # make it an async generator

    mock_indicator = MagicMock(spec=StageIndicator)
    mock_mem = _make_mock_memory()

    with patch("cli.app.StageIndicator", return_value=mock_indicator), \
         patch("cli.app.load_config", return_value={
             "routing": {"default_model": "test-model"},
             "memory": {"max_context_tokens": 8000},
         }), \
         patch("cli.app.create_memory_provider", return_value=mock_mem), \
         patch("cli.app.classify_intent", new_callable=AsyncMock, return_value="general"), \
         patch("cli.app.evaluate_complexity", return_value="low"), \
         patch("cli.app.select_model", return_value="test-model"):

        cli = BrixCLI()
        cli._orchestrator = MagicMock()
        cli._orchestrator.run_stream = MagicMock(return_value=empty_stream())

        await cli._process_streaming("hello")

        # StageIndicator.finish() must have been called
        mock_indicator.finish.assert_called()


# ------------------------------------------------------------------
# Styled prompt + StageIndicator integration tests (Task 3)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_styled_prompt_used():
    """BrixCLI should use styled prompt with ❯ symbol."""
    from cli.app import BrixCLI
    from prompt_toolkit import HTML

    mock_mem = _make_mock_memory()

    with patch("cli.app.load_config", return_value={
        "routing": {"default_model": "test-model"},
        "memory": {"max_context_tokens": 8000},
    }), \
         patch("cli.app.create_memory_provider", return_value=mock_mem):
        cli = BrixCLI()

    session = MagicMock()
    session.prompt_async = AsyncMock(side_effect=EOFError)

    with patch("cli.app.PromptSession", return_value=session):
        try:
            await cli.run()
        except (SystemExit, EOFError):
            pass

    # Verify the prompt contains ❯ (passed as HTML object)
    call_args = session.prompt_async.call_args
    prompt_arg = call_args[0][0] if call_args[0] else call_args[1].get("message", "")
    assert "❯" in str(prompt_arg), "Prompt should contain ❯ symbol"


@pytest.mark.asyncio
async def test_stage_indicator_called_during_streaming():
    """_process_streaming should create and use a StageIndicator."""
    from cli.app import BrixCLI
    from cli.stage_indicator import StageIndicator

    async def fake_stream():
        yield {"type": "text_delta", "text": "Hi"}

    mock_indicator = MagicMock(spec=StageIndicator)
    mock_mem = _make_mock_memory()

    with patch("cli.app.StageIndicator", return_value=mock_indicator), \
         patch("cli.app.load_config", return_value={
             "routing": {"default_model": "test-model"},
             "memory": {"max_context_tokens": 8000},
         }), \
         patch("cli.app.create_memory_provider", return_value=mock_mem), \
         patch("cli.app.classify_intent", new_callable=AsyncMock, return_value="chat"), \
         patch("cli.app.evaluate_complexity", return_value="low"), \
         patch("cli.app.select_model", return_value="test-model"):

        cli = BrixCLI()
        cli._orchestrator = MagicMock()
        cli._orchestrator.run_stream = MagicMock(return_value=fake_stream())

        await cli._process_streaming("hello")

    # update() should have been called for all major stages
    update_calls = [c[0][0] for c in mock_indicator.update.call_args_list]
    assert "Intent" in update_calls
    assert "Complexity" in update_calls
    assert "Route" in update_calls
    assert "Planning" in update_calls


# ------------------------------------------------------------------
# Banner tests (Task 4)
# ------------------------------------------------------------------

def test_banner_uses_rich_console():
    """show_banner should accept a Console and use it for output."""
    from rich.console import Console
    from cli.banner import show_banner

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)

    show_banner(console=console, model="test-model", version="0.1.0", cwd="/tmp")

    output = buf.getvalue()
    assert "BRIX" in output
    assert "test-model" in output


# ------------------------------------------------------------------
# /resume 命令测试
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resume_no_sessions():
    """/resume 无 session 时应提示 'No sessions yet.'"""
    from cli.app import BrixCLI

    mock_mem = _make_mock_memory()
    mock_mem.load_sessions_index.return_value = []

    with patch("cli.app.load_config", return_value={
        "routing": {"default_model": "test-model"},
        "memory": {"max_context_tokens": 8000},
    }), \
         patch("cli.app.create_memory_provider", return_value=mock_mem):
        cli = BrixCLI()

    with patch("builtins.print") as mock_print:
        result = await cli._handle_command("/resume")

    assert result is True
    mock_print.assert_any_call("No sessions yet.")


@pytest.mark.asyncio
async def test_resume_direct_id_match():
    """/resume 有 session 时应列出会话摘要。"""
    from cli.app import BrixCLI

    mock_mem = _make_mock_memory()
    mock_mem.load_sessions_index.return_value = [
        {"id": "abc12345-xxxx", "message_count": 5, "updated": "2026-05-10", "preview": "hello"},
    ]

    with patch("cli.app.load_config", return_value={
        "routing": {"default_model": "test-model"},
        "memory": {"max_context_tokens": 8000},
    }), \
         patch("cli.app.create_memory_provider", return_value=mock_mem):
        cli = BrixCLI()

    with patch("builtins.print") as mock_print:
        result = await cli._handle_command("/resume abc")

    assert result is True
    printed = " ".join(str(c) for call in mock_print.call_args_list for c in call[0])
    assert "abc12345" in printed


@pytest.mark.asyncio
async def test_resume_interactive_select():
    """/resume 无参数时应列出会话摘要。"""
    from cli.app import BrixCLI

    mock_mem = _make_mock_memory()
    session_data = {"id": "abc12345-xxxx", "message_count": 5, "updated": "2026-05-10", "preview": "hello"}
    mock_mem.load_sessions_index.return_value = [session_data]

    with patch("cli.app.load_config", return_value={
        "routing": {"default_model": "test-model"},
        "memory": {"max_context_tokens": 8000},
    }), \
         patch("cli.app.create_memory_provider", return_value=mock_mem):
        cli = BrixCLI()

    with patch("builtins.print") as mock_print:
        result = await cli._handle_command("/resume")

    assert result is True
    printed = " ".join(str(c) for call in mock_print.call_args_list for c in call[0])
    assert "abc12345" in printed


@pytest.mark.asyncio
async def test_resume_lists_sessions():
    """/resume 有 session 时应列出会话信息。"""
    from cli.app import BrixCLI

    mock_mem = _make_mock_memory()
    mock_mem.load_sessions_index.return_value = [
        {"id": "abc12345-xxxx", "message_count": 5},
        {"id": "def67890-yyyy", "message_count": 3},
    ]

    with patch("cli.app.load_config", return_value={
        "routing": {"default_model": "test-model"},
        "memory": {"max_context_tokens": 8000},
    }), \
         patch("cli.app.create_memory_provider", return_value=mock_mem):
        cli = BrixCLI()

    with patch("builtins.print") as mock_print:
        result = await cli._handle_command("/resume")

    assert result is True
    printed = " ".join(str(c) for call in mock_print.call_args_list for c in call[0])
    assert "abc12345" in printed
    assert "def67890" in printed


@pytest.mark.asyncio
async def test_help_shows_resume_no_sessions():
    """/help 应显示 /resume 而非 /sessions。"""
    from cli.app import BrixCLI

    mock_mem = _make_mock_memory()

    with patch("cli.app.load_config", return_value={
        "routing": {"default_model": "test-model"},
        "memory": {"max_context_tokens": 8000},
    }), \
         patch("cli.app.create_memory_provider", return_value=mock_mem):
        cli = BrixCLI()

    with patch("builtins.print") as mock_print:
        result = await cli._handle_command("/help")

    assert result is True
    # 收集所有打印内容
    printed = " ".join(str(c) for call in mock_print.call_args_list for c in call[0])
    assert "/resume" in printed
    assert "/sessions" not in printed
