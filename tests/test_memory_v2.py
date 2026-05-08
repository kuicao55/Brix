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

# ─── Fix 5: save_session re-indexes missing entries ──────────────

class TestSaveSessionReindexesMissing:
    """save_session 应在索引缺失条目时自动补录。"""

    def test_save_session_reindexes_when_entry_missing_from_index(self, tmp_path):
        """索引丢失某条记录后，save_session 应将其重新插入索引。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid = sm.create_session()
        sm.save_session(sid, [{"role": "user", "content": "hello"}])

        # 清空索引（但保留 session 文件）
        index_path = tmp_path / "sessions" / "index.json"
        index_path.write_text(json.dumps([]), encoding="utf-8")

        # list_sessions 因存在未索引的 session 文件会自动重建，
        # 但 save_session 内部的索引更新逻辑走的是 _update_index 路径。
        # 直接验证：save_session 后索引中包含该 session。
        sm.save_session(sid, [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ])

        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == sid
        assert sessions[0]["message_count"] == 2


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


# ─── Fix 6: list_sessions detects stale index ────────────────────

class TestListSessionsStalenessDetection:
    """list_sessions 应检测索引与实际 session 文件的不一致。"""

    def test_list_sessions_detects_new_session_file_not_in_index(self, tmp_path):
        """session 文件存在但索引中没有 → 自动重建索引。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid = sm.create_session()
        sm.save_session(sid, [{"role": "user", "content": "first"}])
        # 清空索引，模拟 crash 导致索引未更新
        index_path = tmp_path / "sessions" / "index.json"
        index_path.write_text(json.dumps([]), encoding="utf-8")

        # list_sessions 应检测到不一致并重建
        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == sid

    def test_list_sessions_no_false_positive_when_index_consistent(self, tmp_path):
        """索引和文件一致时不应触发重建。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid1 = sm.create_session()
        sm.save_session(sid1, [{"role": "user", "content": "first"}])
        sid2 = sm.create_session()
        sm.save_session(sid2, [{"role": "user", "content": "second"}])

        sessions = sm.list_sessions()
        assert len(sessions) == 2
        # 不应触发重建（索引和文件一致）
        ids = {s["id"] for s in sessions}
        assert ids == {sid1, sid2}

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


# ─── Finding 1: Stale index entries not detected ──────────────────────

class TestStaleIndexDetection:
    """list_sessions 应检测索引中有但文件已删除的条目并清理。"""

    def test_list_sessions_removes_stale_index_entry(self, tmp_path):
        """索引中有某 session 但文件已删除 → 该条目应被移除。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid1 = sm.create_session()
        sm.save_session(sid1, [{"role": "user", "content": "first"}])
        sid2 = sm.create_session()
        sm.save_session(sid2, [{"role": "user", "content": "second"}])

        # 删除 sid1 对应的 session 文件
        session_file = tmp_path / "sessions" / f"session-{sid1}.json"
        session_file.unlink()

        # list_sessions 应只返回 sid2
        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == sid2

    def test_stale_entry_persisted_to_index(self, tmp_path):
        """清理后的索引应持久化到磁盘，后续调用不会重新出现。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sid1 = sm.create_session()
        sm.save_session(sid1, [{"role": "user", "content": "first"}])
        sid2 = sm.create_session()
        sm.save_session(sid2, [{"role": "user", "content": "second"}])

        # 删除 sid1
        session_file = tmp_path / "sessions" / f"session-{sid1}.json"
        session_file.unlink()

        sm.list_sessions()

        # 再次调用 list_sessions，不应再出现 sid1
        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == sid2


# ─── Finding 2: Index format assumed to be a list ─────────────────────

class TestIndexFormatNormalization:
    """_load_index 应处理 { "sessions": [...] } 字典格式。"""

    def test_load_index_handles_dict_with_sessions_key(self, tmp_path):
        """index.json 使用 { "sessions": [...] } 格式时应正确解析。"""
        from memory.session import SessionManager
        import uuid as _uuid
        sm = SessionManager(tmp_path)
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        sid = str(_uuid.uuid4())
        session_file = sessions_dir / f"session-{sid}.json"
        session_file.write_text(
            json.dumps([{"role": "user", "content": "hello"}]),
            encoding="utf-8",
        )

        # 写入 dict 格式的 index
        index_data = {
            "sessions": [
                {
                    "id": sid,
                    "created": "2026-05-08T10:00:00Z",
                    "updated": "2026-05-08T10:00:00Z",
                    "message_count": 1,
                    "preview": "hello",
                }
            ]
        }
        (sessions_dir / "index.json").write_text(
            json.dumps(index_data), encoding="utf-8"
        )

        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == sid

    def test_load_index_rebuilds_on_invalid_type(self, tmp_path):
        """index.json 既不是 list 也不是 dict-with-sessions 时应重建。"""
        from memory.session import SessionManager
        import uuid as _uuid
        sm = SessionManager(tmp_path)
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        sid = str(_uuid.uuid4())
        session_file = sessions_dir / f"session-{sid}.json"
        session_file.write_text(
            json.dumps([{"role": "user", "content": "hello"}]),
            encoding="utf-8",
        )

        # 写入无效格式的 index（纯字符串）
        (sessions_dir / "index.json").write_text('"invalid"', encoding="utf-8")

        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == sid


# ─── Finding 3: Rebuild can emit invalid/non-UUID ids ─────────────────

class TestRebuildUUIDValidation:
    """_rebuild_index 应跳过文件名中 sid 不是合法 UUID 的文件。"""

    def test_rebuild_skips_non_uuid_filename(self, tmp_path):
        """session-notaUUID.json 不应出现在重建索引中。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # 有效的 session 文件
        import uuid as _uuid
        valid_sid = str(_uuid.uuid4())
        valid_file = sessions_dir / f"session-{valid_sid}.json"
        valid_file.write_text(
            json.dumps([{"role": "user", "content": "valid"}]),
            encoding="utf-8",
        )

        # 无效文件名（非 UUID 的 sid）
        invalid_file = sessions_dir / "session-notaUUID.json"
        invalid_file.write_text(
            json.dumps([{"role": "user", "content": "invalid"}]),
            encoding="utf-8",
        )

        # 删除索引触发重建
        index_path = sessions_dir / "index.json"
        if index_path.exists():
            index_path.unlink()

        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == valid_sid

    def test_rebuild_skips_uuid_like_but_invalid_filename(self, tmp_path):
        """近似 UUID 但不合法的文件名也应被跳过。"""
        from memory.session import SessionManager
        sm = SessionManager(tmp_path)
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # 有效的 session 文件
        import uuid as _uuid
        valid_sid = str(_uuid.uuid4())
        valid_file = sessions_dir / f"session-{valid_sid}.json"
        valid_file.write_text(
            json.dumps([{"role": "user", "content": "valid"}]),
            encoding="utf-8",
        )

        # 文件名缺少最后一段 hex
        almost_uuid = "550e8400-e29b-41d4-a716-44665544000"
        invalid_file = sessions_dir / f"session-{almost_uuid}.json"
        invalid_file.write_text(
            json.dumps([{"role": "user", "content": "almost"}]),
            encoding="utf-8",
        )

        index_path = sessions_dir / "index.json"
        if index_path.exists():
            index_path.unlink()

        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == valid_sid
