"""Tests for StreamRenderer embedded activity indicator."""
from __future__ import annotations

import io
import time
from unittest.mock import patch

import pytest
from rich.console import Console
from rich.text import Text

from cli.stream_renderer import StreamRenderer


def _make_renderer():
    """Helper: create a StreamRenderer backed by a string buffer."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    return StreamRenderer(console, marker=Text("  ⏺ ", style="green")), buf


class TestActivityIndicator:
    def test_build_display_returns_group(self):
        """_build_display() should return a renderable (Group or Text)."""
        renderer, _ = _make_renderer()
        renderer.start()
        display = renderer._build_display()
        # Should be a Group or Text, not None
        assert display is not None
        renderer.flush()

    def test_indicator_applies_after_idle_threshold(self):
        """Activity indicator should appear when idle > 0.8s with pending content."""
        renderer, _ = _make_renderer()
        renderer.start()
        renderer.rendered = "already rendered"
        renderer.pending = "some text"

        # Simulate idle: set _last_delta_time to 1 second ago
        renderer._last_delta_time = time.time() - 1.0

        display = renderer._build_display()
        # The display should contain the indicator text
        # We verify by checking that the Group has more than one child
        from rich.console import Group
        assert isinstance(display, Group)
        assert len(display.renderables) == 2  # Markdown + indicator
        renderer.flush()

    def test_indicator_hidden_when_recent_delta(self):
        """Activity indicator should NOT appear when delta was recent."""
        renderer, _ = _make_renderer()
        renderer.start()
        renderer.pending = "some text"
        renderer._last_delta_time = time.time()  # just now

        display = renderer._build_display()
        from rich.console import Group
        # Should only have Markdown, no indicator
        if isinstance(display, Group):
            assert len(display.renderables) == 1
        renderer.flush()

    def test_indicator_hidden_when_no_pending(self):
        """Activity indicator should NOT appear when pending is empty."""
        renderer, _ = _make_renderer()
        renderer.start()
        renderer.pending = ""
        renderer._last_delta_time = time.time() - 1.0  # idle

        display = renderer._build_display()
        # No pending content, so either empty Text or single Markdown
        from rich.console import Group
        if isinstance(display, Group):
            assert len(display.renderables) <= 1
        renderer.flush()

    def test_push_delta_resets_idle_timer(self):
        """push_delta() should update _last_delta_time."""
        renderer, _ = _make_renderer()
        renderer.start()
        old_time = renderer._last_delta_time

        with patch("cli.stream_renderer.time") as mock_time:
            mock_time.time.return_value = old_time + 10.0
            renderer.push_delta("new text")

        assert renderer._last_delta_time == old_time + 10.0
        renderer.flush()

    def test_start_initializes_last_delta_time(self):
        """start() should set _last_delta_time to current time."""
        renderer, _ = _make_renderer()
        before = time.time()
        renderer.start()
        after = time.time()
        assert before <= renderer._last_delta_time <= after
        renderer.flush()

    def test_indicator_label_default(self):
        """Default indicator label should be 'Waiting for tool call...'."""
        renderer, _ = _make_renderer()
        assert renderer._indicator_label == "Waiting for tool call..."
