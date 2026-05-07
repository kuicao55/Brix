"""Tests for the flow log module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from log.flow import FlowLog
from log.writer import (
    ensure_log_dir, flush_log, write_jsonl,
    read_all, read_entry, entry_count,
    format_compact_list, format_detail,
)


# ======================================================================
# FlowLog unit tests
# ======================================================================


class TestFlowLogInit:
    def test_trace_is_8_char_hex(self):
        log = FlowLog("hello")
        assert len(log._trace) == 8
        int(log._trace, 16)  # should not raise

    def test_timestamp_is_recent(self):
        from datetime import datetime
        before = datetime.now()
        log = FlowLog("test")
        after = datetime.now()
        assert before <= log._ts <= after

    def test_input_stored(self):
        log = FlowLog("some input")
        assert log._input == "some input"

    def test_steps_empty_initially(self):
        log = FlowLog("test")
        assert log._steps == []

    def test_model_empty_initially(self):
        log = FlowLog("test")
        assert log._model == ""

    def test_error_none_initially(self):
        log = FlowLog("test")
        assert log._error is None


class TestFlowLogStep:
    def test_step_appends_entry(self):
        log = FlowLog("test")
        log.step("memory", msgs=5, window=3)
        assert len(log._steps) == 1
        assert log._steps[0]["m"] == "memory"
        assert log._steps[0]["msgs"] == 5
        assert log._steps[0]["window"] == 3
        assert "at" in log._steps[0]

    def test_multiple_steps(self):
        log = FlowLog("test")
        log.step("memory", msgs=5)
        log.step("intent", result="chat")
        log.step("complexity", result="low")
        assert len(log._steps) == 3

    def test_empty_module_name_ignored(self):
        log = FlowLog("test")
        log.step("", foo="bar")
        assert len(log._steps) == 0


class TestFlowLogSetters:
    def test_set_model(self):
        log = FlowLog("test")
        log.set_model("mimo/mimo-v2-pro")
        assert log._model == "mimo/mimo-v2-pro"

    def test_set_error(self):
        log = FlowLog("test")
        log.set_error("something broke")
        assert log._error == "something broke"


class TestFlowLogFinish:
    def test_finish_returns_expected_keys(self):
        log = FlowLog("test")
        entry = log.finish()
        expected = {"ts", "trace", "input", "steps", "model",
                    "iters", "tools", "llm_calls", "ms_total", "error"}
        assert set(entry.keys()) == expected

    def test_finish_counts_llm_calls(self):
        log = FlowLog("test")
        log.step("intent", result="chat", ms=100)
        log.step("orch_plan", iter=1, tools=[], ms=200)
        log.step("tool_exec", name="calc", ms=5)
        entry = log.finish()
        # intent and orch_plan have "ms" -> 2 llm calls
        assert entry["llm_calls"] == 2

    def test_finish_counts_tools(self):
        log = FlowLog("test")
        log.step("tool_exec", name="calc")
        log.step("tool_exec", name="weather")
        entry = log.finish()
        assert entry["tools"] == 2

    def test_finish_counts_iters(self):
        log = FlowLog("test")
        log.step("orch_plan", iter=1)
        log.step("orch_plan", iter=2)
        entry = log.finish()
        assert entry["iters"] == 2

    def test_finish_with_no_steps(self):
        log = FlowLog("test")
        entry = log.finish()
        assert entry["llm_calls"] == 0
        assert entry["tools"] == 0
        assert entry["iters"] == 0
        assert entry["error"] is None

    def test_finish_includes_error(self):
        log = FlowLog("test")
        log.set_error("boom")
        entry = log.finish()
        assert entry["error"] == "boom"


# ======================================================================
# Writer unit tests
# ======================================================================


class TestWriterEnsureLogDir:
    def test_creates_directory(self, tmp_path):
        target = tmp_path / "logs"
        with patch("log.writer.LOG_DIR", target):
            ensure_log_dir()
            assert target.is_dir()

    def test_idempotent(self, tmp_path):
        target = tmp_path / "logs"
        with patch("log.writer.LOG_DIR", target):
            ensure_log_dir()
            ensure_log_dir()  # should not raise
            assert target.is_dir()


class TestWriterJsonl:
    def test_creates_file(self, tmp_path):
        fp = tmp_path / "test.jsonl"
        with patch("log.writer.JSONL_PATH", fp):
            write_jsonl({"ts": "2026-01-01", "trace": "abc"})
        assert fp.exists()
        line = fp.read_text().strip()
        data = json.loads(line)
        assert data["trace"] == "abc"

    def test_appends_multiple(self, tmp_path):
        fp = tmp_path / "test.jsonl"
        with patch("log.writer.JSONL_PATH", fp):
            write_jsonl({"a": 1})
            write_jsonl({"b": 2})
        lines = fp.read_text().strip().split("\n")
        assert len(lines) == 2


class TestWriterFlushLog:
    def test_creates_jsonl_file(self, tmp_path):
        jsonl_fp = tmp_path / "brix.jsonl"
        with patch("log.writer.JSONL_PATH", jsonl_fp):
            log = FlowLog("test input")
            log.step("memory", msgs=3, window=2)
            flush_log(log)
        assert jsonl_fp.exists()

    def test_jsonl_is_valid(self, tmp_path):
        jsonl_fp = tmp_path / "brix.jsonl"
        with patch("log.writer.JSONL_PATH", jsonl_fp):
            log = FlowLog("test")
            flush_log(log)
        data = json.loads(jsonl_fp.read_text().strip())
        assert "trace" in data
        assert "steps" in data


class TestWriterReadAll:
    def test_missing_file_returns_empty(self, tmp_path):
        fp = tmp_path / "nonexistent.jsonl"
        with patch("log.writer.JSONL_PATH", fp):
            result = read_all()
        assert result == []

    def test_empty_file_returns_empty(self, tmp_path):
        fp = tmp_path / "empty.jsonl"
        fp.touch()
        with patch("log.writer.JSONL_PATH", fp):
            result = read_all()
        assert result == []

    def test_reads_all_entries(self, tmp_path):
        fp = tmp_path / "test.jsonl"
        with open(fp, "w") as f:
            for i in range(5):
                f.write(json.dumps({"i": i}) + "\n")
        with patch("log.writer.JSONL_PATH", fp):
            result = read_all()
        assert len(result) == 5
        assert result[0]["i"] == 0
        assert result[4]["i"] == 4

    def test_skips_corrupted_lines(self, tmp_path):
        fp = tmp_path / "test.jsonl"
        with open(fp, "w") as f:
            f.write(json.dumps({"ok": True}) + "\n")
            f.write("not valid json\n")
            f.write(json.dumps({"ok": True}) + "\n")
        with patch("log.writer.JSONL_PATH", fp):
            result = read_all()
        assert len(result) == 2


class TestWriterReadEntry:
    def test_reads_by_index(self, tmp_path):
        fp = tmp_path / "test.jsonl"
        with open(fp, "w") as f:
            for i in range(5):
                f.write(json.dumps({"i": i}) + "\n")
        with patch("log.writer.JSONL_PATH", fp):
            assert read_entry(1)["i"] == 0
            assert read_entry(3)["i"] == 2
            assert read_entry(5)["i"] == 4

    def test_out_of_range_returns_none(self, tmp_path):
        fp = tmp_path / "test.jsonl"
        with open(fp, "w") as f:
            f.write(json.dumps({"i": 0}) + "\n")
        with patch("log.writer.JSONL_PATH", fp):
            assert read_entry(0) is None
            assert read_entry(2) is None

    def test_index_zero_returns_none(self, tmp_path):
        fp = tmp_path / "test.jsonl"
        with patch("log.writer.JSONL_PATH", fp):
            assert read_entry(0) is None


class TestWriterEntryCount:
    def test_counts_entries(self, tmp_path):
        fp = tmp_path / "test.jsonl"
        with open(fp, "w") as f:
            for i in range(7):
                f.write(json.dumps({"i": i}) + "\n")
        with patch("log.writer.JSONL_PATH", fp):
            assert entry_count() == 7

    def test_missing_file_returns_zero(self, tmp_path):
        fp = tmp_path / "nonexistent.jsonl"
        with patch("log.writer.JSONL_PATH", fp):
            assert entry_count() == 0


class TestFormatCompactList:
    def test_format_entries(self):
        entries = [
            {"ts": "2026-05-04T10:00:00", "trace": "abc12345",
             "input": "hello", "ms_total": 100, "error": None},
            {"ts": "2026-05-04T10:01:00", "trace": "def67890",
             "input": "world", "ms_total": 200, "error": "fail"},
        ]
        result = format_compact_list(entries, start_index=1)
        assert "#1" in result
        assert "#2" in result
        assert "abc12345" in result
        assert "OK" in result
        assert "ERR" in result
        assert '"hello"' in result


class TestFormatDetail:
    def test_format_entry(self):
        entry = {
            "ts": "2026-05-04T10:00:00",
            "trace": "abc12345",
            "input": "hello world",
            "model": "test-model",
            "ms_total": 500,
            "llm_calls": 2,
            "tools": 1,
            "iters": 2,
            "error": None,
            "steps": [
                {"m": "memory", "msgs": 3, "window": 2},
                {"m": "intent", "result": "chat", "via": "llm", "ms": 100},
            ],
        }
        result = format_detail(entry)
        assert "abc12345" in result
        assert "hello world" in result
        assert "test-model" in result
        assert "[1] memory" in result
        assert "[2] intent" in result
        assert "msgs: 3" in result
        assert "500ms" in result

    def test_format_entry_with_error(self):
        entry = {
            "ts": "2026-05-04T10:00:00",
            "trace": "abc12345",
            "input": "test",
            "model": "m",
            "ms_total": 0,
            "llm_calls": 0,
            "tools": 0,
            "iters": 0,
            "error": "something broke",
            "steps": [],
        }
        result = format_detail(entry)
        assert "ERR" in result
        assert "something broke" in result


# ======================================================================
# Integration: FlowLog + /log command
# ======================================================================


class TestLogCommand:
    def test_log_command_no_logs(self, tmp_path):
        fp = tmp_path / "empty.jsonl"
        with patch("log.writer.JSONL_PATH", fp):
            result = entry_count()
        assert result == 0
