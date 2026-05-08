"""M7 记忆系统重构测试。"""
import pytest
from pathlib import Path


class TestSessionManager:
    """SessionManager CRUD 测试。"""

    def test_create_session_returns_uuid(self, tmp_path):
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid = sm.create_session()
        assert isinstance(sid, str)
        assert len(sid) == 36  # UUID format

    def test_save_and_load_session(self, tmp_path):
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid = sm.create_session()
        messages = [
            {"role": "user", "content": "hello", "timestamp": "2026-05-08T10:00:00Z"},
            {"role": "assistant", "content": "hi", "timestamp": "2026-05-08T10:00:01Z"},
        ]
        sm.save_session(sid, messages)
        loaded = sm.load_session(sid)
        assert len(loaded) == 2
        assert loaded[0]["role"] == "user"
        assert loaded[1]["content"] == "hi"

    def test_list_sessions(self, tmp_path):
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid1 = sm.create_session()
        sm.save_session(sid1, [{"role": "user", "content": "first", "timestamp": "2026-05-08T10:00:00Z"}])
        sid2 = sm.create_session()
        sm.save_session(sid2, [{"role": "user", "content": "second", "timestamp": "2026-05-08T11:00:00Z"}])
        sessions = sm.list_sessions()
        assert len(sessions) == 2
        # Newest first
        assert sessions[0]["id"] == sid2
        assert sessions[1]["id"] == sid1

    def test_session_index_updated_on_save(self, tmp_path):
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid = sm.create_session()
        sm.save_session(sid, [{"role": "user", "content": "test message", "timestamp": "2026-05-08T10:00:00Z"}])
        sessions = sm.list_sessions()
        assert sessions[0]["message_count"] == 1
        assert "preview" in sessions[0]

    def test_load_nonexistent_session_raises(self, tmp_path):
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        with pytest.raises(FileNotFoundError):
            sm.load_session("nonexistent-id")


class TestSoulManager:
    """SoulManager 读写测试。"""

    def test_load_returns_empty_when_missing(self, tmp_path):
        from memory.soul import SoulManager
        sm = SoulManager(tmp_path)
        assert sm.load() == ""
        assert sm.exists() is False

    def test_save_and_load(self, tmp_path):
        from memory.soul import SoulManager
        sm = SoulManager(tmp_path)
        content = "# Soul\n\nI am Brix."
        sm.save(content)
        assert sm.load() == content
        assert sm.exists() is True

    def test_exists(self, tmp_path):
        from memory.soul import SoulManager
        sm = SoulManager(tmp_path)
        assert sm.exists() is False
        sm.save("content")
        assert sm.exists() is True


class TestUserMemoryManager:
    """UserMemoryManager 读写测试。"""

    def test_load_returns_empty_when_missing(self, tmp_path):
        from memory.user import UserMemoryManager
        um = UserMemoryManager(tmp_path)
        assert um.load() == ""
        assert um.exists() is False

    def test_save_and_load(self, tmp_path):
        from memory.user import UserMemoryManager
        um = UserMemoryManager(tmp_path)
        content = "# User\n\nName: kuicao"
        um.save(content)
        assert um.load() == content
        assert um.exists() is True

    def test_exists(self, tmp_path):
        from memory.user import UserMemoryManager
        um = UserMemoryManager(tmp_path)
        assert um.exists() is False
        um.save("content")
        assert um.exists() is True
