"""Tests for StageIndicator pipeline stage progress display."""

import io

from rich.console import Console

from cli.stage_indicator import StageIndicator
from cli.spinner import Spinner


def _make_indicator():
    """Helper: create a StageIndicator backed by a string buffer."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    return StageIndicator(console), buf


class TestStageIndicatorImport:
    def test_stage_indicator_import(self):
        """StageIndicator is importable from cli.stage_indicator."""
        assert StageIndicator is not None


class TestStageDone:
    def test_stage_done_prints_completion_line(self):
        """stage_done prints stage name and elapsed time formatted to 1 decimal."""
        indicator, buf = _make_indicator()
        indicator.stage_done("Memory", 1.234)
        output = buf.getvalue()
        assert "Memory" in output
        assert "1.2s" in output

    def test_stage_done_includes_detail(self):
        """stage_done appends detail text when provided."""
        indicator, buf = _make_indicator()
        indicator.stage_done("Route", 0.5, detail="3 paths")
        output = buf.getvalue()
        assert "Route" in output
        assert "3 paths" in output

    def test_stage_done_no_detail_omits_detail(self):
        """stage_done with no detail does not leave trailing double-space artifacts."""
        indicator, buf = _make_indicator()
        indicator.stage_done("Planning", 0.8)
        output = buf.getvalue()
        assert "  " * 2 not in output.replace("Planning", "").strip().split("0.8")[0]


class TestStageActive:
    def test_stage_active_returns_spinner(self):
        """stage_active returns a Spinner instance."""
        indicator, _ = _make_indicator()
        spinner = indicator.stage_active("Intent")
        assert isinstance(spinner, Spinner)
        # Clean up: stop the spinner thread
        spinner.finish("cleanup")


class TestSpinnerLeak:
    def test_stage_active_stops_previous_spinner(self):
        """Calling stage_active twice stops the first spinner."""
        indicator, _ = _make_indicator()
        first_spinner = indicator.stage_active("Intent")
        # The first spinner should be running
        assert first_spinner.running is True
        # Start a second spinner — this must stop the first one
        indicator.stage_active("Memory")
        # First spinner should now be stopped (thread leak prevented)
        assert first_spinner.running is False

    def test_stage_active_silently_stops_previous_spinner(self):
        """Calling stage_active twice does NOT print 'Done' for the first spinner."""
        indicator, buf = _make_indicator()
        indicator.stage_active("Intent")
        indicator.stage_active("Memory")
        output = buf.getvalue()
        # No "Done" should appear — the first spinner was stopped silently
        assert "Done" not in output


class TestStageDoneStopsSpinner:
    def test_stage_done_stops_active_spinner(self):
        """stage_done() stops the active spinner started by stage_active()."""
        indicator, buf = _make_indicator()
        spinner = indicator.stage_active("Intent")
        assert spinner.running is True
        indicator.stage_done("Intent", 1.0)
        assert spinner.running is False


class TestMarkupEscape:
    def test_stage_done_escapes_markup(self):
        """stage_done escapes Rich markup in name and detail."""
        indicator, buf = _make_indicator()
        indicator.stage_done("[bold]injected[/bold]", 1.0, detail="[red]bad[/red]")
        output = buf.getvalue()
        # The literal bracket text should appear (escaped), not styled output
        assert "[bold]injected[/bold]" in output
        assert "[red]bad[/red]" in output


class TestSpinnerStop:
    def test_spinner_stop_stops_thread(self):
        """Spinner.stop() stops the animation thread."""
        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True, width=80)
        spinner = Spinner(console, label="Test")
        spinner.start()
        assert spinner.running is True
        spinner.stop()
        assert spinner.running is False

    def test_spinner_stop_does_not_print(self):
        """Spinner.stop() does NOT print a 'Done' message (unlike finish)."""
        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True, width=80)
        spinner = Spinner(console, label="Test")
        spinner.start()
        spinner.stop()
        output = buf.getvalue()
        # stop() should not print "Done" or any visible message
        # (Rich Live may emit terminal control sequences, that's OK)
        assert "Done" not in output
        assert "\u2713" not in output  # no checkmark printed


class TestFinish:
    def test_finish_stops_active_spinner(self):
        """finish() stops the active spinner without error."""
        indicator, _ = _make_indicator()
        indicator.stage_active("Complexity")
        indicator.finish()  # should not raise
