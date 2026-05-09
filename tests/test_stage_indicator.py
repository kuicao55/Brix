"""Tests for StageIndicator — unified loading spinner."""

import io
from unittest.mock import MagicMock

import pytest

from rich.console import Console

from cli.stage_indicator import StageIndicator
from cli.spinner import Spinner


def _make_indicator():
    """Helper: create a StageIndicator backed by a string buffer."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=80)
    return StageIndicator(console), buf


class TestStageIndicatorImport:
    def test_import(self):
        """StageIndicator is importable from cli.stage_indicator."""
        assert StageIndicator is not None


class TestInit:
    def test_starts_spinner_on_init(self):
        """Constructor starts the spinner immediately."""
        indicator, _ = _make_indicator()
        assert indicator._spinner.running is True
        # cleanup
        indicator.finish()


class TestUpdate:
    def test_update_changes_label(self):
        """update() changes the spinner label."""
        indicator, _ = _make_indicator()
        indicator.update("Planning")
        assert indicator._spinner.label == "Planning..."
        # cleanup
        indicator.finish()

    def test_update_unknown_stage_uses_working(self):
        """update() with unknown stage uses 'Working...' label."""
        indicator, _ = _make_indicator()
        indicator.update("UnknownStage")
        assert indicator._spinner.label == "Working..."
        indicator.finish()


class TestFinish:
    def test_finish_stops_spinner(self):
        """finish() stops the spinner without error."""
        indicator, _ = _make_indicator()
        indicator.finish()
        assert indicator._spinner.running is False

    def test_finish_is_idempotent(self):
        """Calling finish() twice does not raise."""
        indicator, _ = _make_indicator()
        indicator.finish()
        indicator.finish()  # should not raise

    def test_finish_respects_finished_flag(self):
        """finish() should not call spinner.stop() if already finished."""
        indicator, _ = _make_indicator()
        indicator._finished = True
        # finish() should not raise even though spinner may still be running
        indicator.finish()


class TestStopSilent:
    def test_stop_silent_stops_spinner(self):
        """stop_silent() stops the spinner without printing."""
        indicator, _ = _make_indicator()
        indicator.stop_silent()
        assert indicator._spinner.running is False
        assert indicator._finished is True

    def test_stop_silent_prevents_update(self):
        """After stop_silent(), update() should be a no-op."""
        indicator, _ = _make_indicator()
        indicator.stop_silent()
        indicator.update("Planning")  # should not raise
        # label should not change since _finished is True
        assert indicator._finished is True

    def test_stop_silent_prevents_finish(self):
        """After stop_silent(), finish() should be a no-op."""
        indicator, _ = _make_indicator()
        indicator.stop_silent()
        indicator.finish()  # should not raise, should be no-op
        assert indicator._finished is True
