"""M7 记忆系统重构测试。"""
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch


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
        # 使用合法 UUID 但该会话不存在
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(FileNotFoundError):
            sm.load_session(fake_uuid)


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


# ─── Fix 1: Path traversal via unsanitized session_id ────────────────

class TestSessionIdValidation:
    """session_id 必须是合法 UUID，防止路径穿越。"""

    def test_save_session_rejects_path_traversal_dots(self, tmp_path):
        """session_id 包含 '..' 应被拒绝。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        malicious_id = "../../etc/passwd"
        with pytest.raises(ValueError):
            sm.save_session(malicious_id, [{"role": "user", "content": "x"}])

    def test_save_session_rejects_path_separator(self, tmp_path):
        """session_id 包含 '/' 应被拒绝。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        malicious_id = "abc/../../secret"
        with pytest.raises(ValueError):
            sm.save_session(malicious_id, [{"role": "user", "content": "x"}])

    def test_save_session_rejects_backslash_separator(self, tmp_path):
        """session_id 包含 '\\' 应被拒绝（Windows 路径）。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        malicious_id = "abc\\..\\secret"
        with pytest.raises(ValueError):
            sm.save_session(malicious_id, [{"role": "user", "content": "x"}])

    def test_load_session_rejects_path_traversal(self, tmp_path):
        """load_session 对非法 session_id 也应拒绝。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        malicious_id = "../outside"
        with pytest.raises(ValueError):
            sm.load_session(malicious_id)

    def test_save_session_accepts_valid_uuid(self, tmp_path):
        """合法 UUID 应正常工作。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid = sm.create_session()
        sm.save_session(sid, [{"role": "user", "content": "ok"}])
        loaded = sm.load_session(sid)
        assert len(loaded) == 1


# ─── Fix 2: Index updates non-atomic across threads/processes ────────

class TestIndexLocking:
    """索引读-改-写操作必须加文件锁。"""

    def test_concurrent_create_sessions_produce_distinct_ids(self, tmp_path):
        """并发 create_session 不应丢失条目。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        import concurrent.futures
        ids = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(sm.create_session) for _ in range(10)]
            ids = [f.result() for f in futures]
        # 所有 ID 唯一
        assert len(set(ids)) == 10
        # 索引包含全部 10 条
        sessions = sm.list_sessions()
        assert len(sessions) == 10

    def test_concurrent_save_sessions_dont_lose_data(self, tmp_path):
        """并发 save_session 不应互相覆盖索引条目。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        import concurrent.futures
        sids = [sm.create_session() for _ in range(5)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futs = [
                pool.submit(sm.save_session, sid, [{"role": "user", "content": f"msg-{sid[:8]}"}])
                for sid in sids
            ]
            concurrent.futures.wait(futs)
        sessions = sm.list_sessions()
        assert len(sessions) == 5
        # 每条都有 message_count=1
        for s in sessions:
            assert s["message_count"] == 1


# ─── Fix 3: Silent index corruption fallback ─────────────────────────

class TestIndexCorruptionRecovery:
    """索引损坏时应从 session 文件重建，而非返回空列表。"""

    def test_corrupted_index_rebuilds_from_session_files(self, tmp_path):
        """index.json 损坏后，list_sessions 应从 session-*.json 重建。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid1 = sm.create_session()
        sm.save_session(sid1, [{"role": "user", "content": "first", "timestamp": "2026-05-08T10:00:00Z"}])
        sid2 = sm.create_session()
        sm.save_session(sid2, [{"role": "user", "content": "second", "timestamp": "2026-05-08T11:00:00Z"}])
        # 写入损坏的 index.json
        index_path = tmp_path / "sessions" / "index.json"
        index_path.write_text("NOT VALID JSON {{{", encoding="utf-8")
        # list_sessions 应该重建并返回 2 条
        sessions = sm.list_sessions()
        assert len(sessions) == 2
        recovered_ids = {s["id"] for s in sessions}
        assert sid1 in recovered_ids
        assert sid2 in recovered_ids

    def test_corrupted_index_rebuild_preserves_message_count(self, tmp_path):
        """重建后的索引应包含正确的 message_count。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid = sm.create_session()
        msgs = [
            {"role": "user", "content": "hello", "timestamp": "2026-05-08T10:00:00Z"},
            {"role": "assistant", "content": "hi", "timestamp": "2026-05-08T10:00:01Z"},
        ]
        sm.save_session(sid, msgs)
        # 损坏索引
        index_path = tmp_path / "sessions" / "index.json"
        index_path.write_text("{garbage", encoding="utf-8")
        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["message_count"] == 2


# ─── Fix 4: Soul/User writes not atomic ──────────────────────────────

class TestAtomicWrites:
    """soul.md 和 user.md 的写入必须是原子操作。"""

    def test_soul_save_is_atomic(self, tmp_path):
        """SoulManager.save 应使用原子写入，不留下临时文件。"""
        from memory.soul import SoulManager
        sm = SoulManager(tmp_path)
        sm.save("initial content")
        sm.save("updated content")
        assert sm.load() == "updated content"
        # 不应留下临时文件
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_user_save_is_atomic(self, tmp_path):
        """UserMemoryManager.save 应使用原子写入，不留下临时文件。"""
        from memory.user import UserMemoryManager
        um = UserMemoryManager(tmp_path)
        um.save("initial content")
        um.save("updated content")
        assert um.load() == "updated content"
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_soul_save_on_write_failure_preserves_old_content(self, tmp_path):
        """SoulManager.save 失败时不应丢失旧内容。"""
        from memory.soul import SoulManager
        sm = SoulManager(tmp_path)
        sm.save("original content")
        # 模拟写入过程中 OSError（os.fdopen 在 save 中被调用）
        with patch("memory.soul.os.fdopen", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                sm.save("new content that should fail")
        # 旧内容应保留
        assert sm.load() == "original content"

    def test_user_save_on_write_failure_preserves_old_content(self, tmp_path):
        """UserMemoryManager.save 失败时不应丢失旧内容。"""
        from memory.user import UserMemoryManager
        um = UserMemoryManager(tmp_path)
        um.save("original content")
        with patch("memory.user.os.fdopen", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                um.save("new content that should fail")
        assert um.load() == "original content"
