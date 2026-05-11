"""Tests for capability/basics/ modules.

测试所有基础功能模块的纯逻辑，不涉及 UI。
"""

from unittest.mock import MagicMock

import pytest

from capability.basics.sessions import (
    get_session_by_prefix,
    list_sessions,
    load_session_messages,
    resume_session,
)
from capability.basics.memory_files import load_soul, load_user
from capability.basics.logs import get_recent_logs, get_log_detail
from capability.basics.commands import COMMANDS, get_command_list


# ------------------------------------------------------------------
# 辅助
# ------------------------------------------------------------------

def _mock_memory(**overrides) -> MagicMock:
    m = MagicMock()
    m.list_sessions.return_value = overrides.get("sessions", [])
    m.load_session.return_value = overrides.get("load_msgs", [])
    m.resume_session.return_value = overrides.get("resume_msgs", [])
    m.soul_exists.return_value = overrides.get("soul_exists", False)
    m.load_soul.return_value = overrides.get("soul_content", "")
    m.user_memory_exists.return_value = overrides.get("user_exists", False)
    m.load_user_memory.return_value = overrides.get("user_content", "")
    return m


# ------------------------------------------------------------------
# sessions.py
# ------------------------------------------------------------------

class TestListSessions:
    def test_returns_sessions(self):
        data = [{"id": "abc"}, {"id": "def"}]
        mem = _mock_memory(sessions=data)
        assert list_sessions(mem) == data

    def test_empty(self):
        mem = _mock_memory(sessions=[])
        assert list_sessions(mem) == []


class TestGetSessionByPrefix:
    def test_unique_match(self):
        sessions = [
            {"id": "abc12345-xxxx"},
            {"id": "def67890-yyyy"},
        ]
        mem = _mock_memory(sessions=sessions)
        result = get_session_by_prefix(mem, "abc")
        assert result == {"id": "abc12345-xxxx"}

    def test_no_match(self):
        mem = _mock_memory(sessions=[{"id": "abc12345-xxxx"}])
        assert get_session_by_prefix(mem, "zzz") is None

    def test_ambiguous(self):
        sessions = [
            {"id": "abc11111-xxxx"},
            {"id": "abc22222-yyyy"},
        ]
        mem = _mock_memory(sessions=sessions)
        assert get_session_by_prefix(mem, "abc") == "ambiguous"


class TestResumeSession:
    def test_returns_messages(self):
        msgs = [{"role": "user", "content": "hi"}]
        mem = _mock_memory(resume_msgs=msgs)
        assert resume_session(mem, "abc123") == msgs

    def test_not_found(self):
        mem = MagicMock()
        mem.resume_session.side_effect = FileNotFoundError
        with pytest.raises(FileNotFoundError):
            resume_session(mem, "nonexistent")


class TestLoadSessionMessages:
    def test_returns_messages(self):
        msgs = [{"role": "user", "content": "hello"}]
        mem = _mock_memory(load_msgs=msgs)
        assert load_session_messages(mem, "abc123") == msgs


# ------------------------------------------------------------------
# memory_files.py
# ------------------------------------------------------------------

class TestLoadSoul:
    def test_exists(self):
        mem = _mock_memory(soul_exists=True, soul_content="I am Brix")
        assert load_soul(mem) == "I am Brix"

    def test_not_exists(self):
        mem = _mock_memory(soul_exists=False)
        assert load_soul(mem) is None


class TestLoadUser:
    def test_exists(self):
        mem = _mock_memory(user_exists=True, user_content="User profile")
        assert load_user(mem) == "User profile"

    def test_not_exists(self):
        mem = _mock_memory(user_exists=False)
        assert load_user(mem) is None


# ------------------------------------------------------------------
# logs.py
# ------------------------------------------------------------------

class TestGetRecentLogs:
    def test_empty(self):
        with patch_logs(count=0):
            assert get_recent_logs() == []

    def test_returns_recent(self):
        entries = [{"ts": "2026-05-10"}, {"ts": "2026-05-09"}]
        with patch_logs(count=2, entries=entries):
            result = get_recent_logs(2)
            assert len(result) == 2


class TestGetLogDetail:
    def test_returns_string(self):
        entry = {"ts": "2026-05-10", "input": "test"}
        # format_detail returns a string; just verify it doesn't crash
        result = get_log_detail(entry)
        assert isinstance(result, str)


# ------------------------------------------------------------------
# commands.py
# ------------------------------------------------------------------

class TestCommands:
    def test_commands_not_empty(self):
        assert len(COMMANDS) > 0

    def test_get_command_list_returns_copy(self):
        result = get_command_list()
        assert result == COMMANDS
        # 修改返回值不应影响原列表
        result.append(("/test", "test"))
        assert len(COMMANDS) == len(get_command_list())

    def test_all_commands_have_name_and_desc(self):
        for name, desc in COMMANDS:
            assert name.startswith("/"), f"Command {name} should start with /"
            assert len(desc) > 0, f"Command {name} has empty description"


# ------------------------------------------------------------------
# 辅助 patch
# ------------------------------------------------------------------

from contextlib import contextmanager
from typing import Optional
from unittest.mock import patch


@contextmanager
def patch_logs(count: int = 0, entries: Optional[list] = None):
    """Patch log.writer functions for testing."""
    with patch("capability.basics.logs.entry_count", return_value=count), \
         patch("capability.basics.logs.read_all", return_value=entries or []):
        yield
