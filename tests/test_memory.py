"""Tests for the memory storage and strategy (Task 5).

TDD: These tests are written BEFORE the implementation.
Step 2 (RED): all should fail with ModuleNotFoundError.
Step 4 (GREEN): all should pass after implementation.
"""

import json
import logging
import pytest
from memory.session import SessionManager
from memory.storage import MemoryStorage
from memory.strategy import MemoryStrategy


def test_memory_storage_save_and_load(tmp_path):
    sm = SessionManager(tmp_path)
    sid = sm.create_session()
    storage = MemoryStorage(session_manager=sm, session_id=sid)
    storage.add_message("user", "hello")
    storage.add_message("assistant", "hi there")
    storage.save()

    # Reload via SessionManager
    messages = sm.load_session(sid)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["content"] == "hi there"


def test_memory_storage_limit(tmp_path):
    sm = SessionManager(tmp_path)
    sid = sm.create_session()
    storage = MemoryStorage(session_manager=sm, session_id=sid)
    for i in range(10):
        storage.add_message("user", f"msg {i}")

    history = storage.get_history(limit=3)
    assert len(history) == 3


def test_memory_strategy_should_save(tmp_path):
    from memory.soul import SoulManager
    from memory.user import UserMemoryManager
    strategy = MemoryStrategy(soul_manager=SoulManager(tmp_path), user_manager=UserMemoryManager(tmp_path))
    assert strategy.should_save({"role": "user", "content": "hello"}) is True


def test_memory_strategy_context_window(tmp_path):
    from memory.soul import SoulManager
    from memory.user import UserMemoryManager
    strategy = MemoryStrategy(soul_manager=SoulManager(tmp_path), user_manager=UserMemoryManager(tmp_path))
    history = [{"role": "user", "content": f"message {i}"} for i in range(100)]
    # Each "message N" is ~3 tokens; 100 messages = ~300 tokens
    # Use limit of 100 to force truncation
    window = strategy.get_context_window(history, max_tokens=100)
    assert len(window) < len(history)
    assert len(window) > 0


def test_token_counting_truncation(tmp_path):
    """MemoryStrategy should truncate by tokens, not characters."""
    from memory.soul import SoulManager
    from memory.user import UserMemoryManager
    strategy = MemoryStrategy(soul_manager=SoulManager(tmp_path), user_manager=UserMemoryManager(tmp_path), max_tokens=50)  # very small limit

    # Create messages that would fit in chars but not tokens
    # A 50-char message is roughly 12-15 tokens
    history = [
        {"role": "user", "content": "Hello, how are you doing today? I hope everything is fine."},
        {"role": "assistant", "content": "I am doing well, thank you for asking! How can I help?"},
        {"role": "user", "content": "Can you help me with a Python question about async?"},
        {"role": "assistant", "content": "Of course! What specifically about async would you like to know?"},
    ]

    window = strategy.get_context_window(history)
    # With 50 token limit, should not include all messages
    assert len(window) < len(history)


def test_system_message_preservation(tmp_path):
    """System messages should always be preserved."""
    from memory.soul import SoulManager
    from memory.user import UserMemoryManager
    strategy = MemoryStrategy(soul_manager=SoulManager(tmp_path), user_manager=UserMemoryManager(tmp_path), max_tokens=10)

    history = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello " * 100},  # large message to push over limit
    ]

    window = strategy.get_context_window(history)
    # System message should always be in the window
    assert any(m.get("role") == "system" for m in window)


def test_graceful_fallback_without_tiktoken(tmp_path):
    """Should fall back to char-based counting if tiktoken fails."""
    from memory.soul import SoulManager
    from memory.user import UserMemoryManager
    strategy = MemoryStrategy(soul_manager=SoulManager(tmp_path), user_manager=UserMemoryManager(tmp_path), max_tokens=4000)

    # Monkey-patch to simulate tiktoken failure
    original_encoder = strategy._encoder
    strategy._encoder = None

    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    window = strategy.get_context_window(history)
    assert len(window) == 2  # both messages fit

    strategy._encoder = original_encoder


def test_clear_persists_after_restart(tmp_path):
    """Cleared state should survive creating a new MemoryStorage instance."""
    sm = SessionManager(tmp_path)
    sid = sm.create_session()
    # First instance: add messages and save
    storage = MemoryStorage(session_manager=sm, session_id=sid)
    storage.add_message("user", "hello")
    storage.add_message("assistant", "hi there")
    storage.save()

    # Verify messages exist on disk via SessionManager
    messages = sm.load_session(sid)
    assert len(messages) == 2

    # Clear and save (simulating /clear command)
    storage.clear()
    storage.save()

    # "Restart" — reload from SessionManager should see empty history
    messages = sm.load_session(sid)
    assert len(messages) == 0


# --- Quality Review edge cases ---


def test_count_tokens_none_content(tmp_path):
    """_count_tokens should return 0 for None or empty content, not crash."""
    from memory.soul import SoulManager
    from memory.user import UserMemoryManager
    strategy = MemoryStrategy(soul_manager=SoulManager(tmp_path), user_manager=UserMemoryManager(tmp_path))
    assert strategy._count_tokens("") == 0
    assert strategy._count_tokens(None) == 0


def test_count_tokens_none_content_fallback(tmp_path):
    """_count_tokens with char-based fallback should also handle None/empty."""
    from memory.soul import SoulManager
    from memory.user import UserMemoryManager
    strategy = MemoryStrategy(soul_manager=SoulManager(tmp_path), user_manager=UserMemoryManager(tmp_path))
    strategy._encoder = None  # force char-based fallback
    assert strategy._count_tokens("") == 0
    assert strategy._count_tokens(None) == 0


def test_context_window_none_content_messages(tmp_path):
    """Messages with content=None (e.g. tool-call messages) should not crash."""
    from memory.soul import SoulManager
    from memory.user import UserMemoryManager
    strategy = MemoryStrategy(soul_manager=SoulManager(tmp_path), user_manager=UserMemoryManager(tmp_path), max_tokens=1000)
    history = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": None, "tool_calls": [{"name": "foo"}]},
        {"role": "user", "content": "Continue"},
    ]
    window = strategy.get_context_window(history)
    assert len(window) == 4  # all fit within 1000 tokens


def test_context_window_system_exceeds_budget(tmp_path):
    """If system messages alone exceed the token limit, truncate to fit."""
    from memory.soul import SoulManager
    from memory.user import UserMemoryManager
    strategy = MemoryStrategy(soul_manager=SoulManager(tmp_path), user_manager=UserMemoryManager(tmp_path), max_tokens=5)
    long_system = "You are a very helpful assistant. " * 50  # well over 5 tokens
    history = [
        {"role": "system", "content": long_system},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    window = strategy.get_context_window(history)
    # Should contain truncated system message, no non-system messages
    assert len(window) == 1
    assert window[0]["role"] == "system"
    assert "[truncated]" in window[0]["content"]
    assert len(window[0]["content"]) < len(long_system)


def test_context_window_system_exceeds_budget_exact_boundary(tmp_path):
    """Edge case: system messages exactly at the budget boundary."""
    from memory.soul import SoulManager
    from memory.user import UserMemoryManager
    strategy = MemoryStrategy(soul_manager=SoulManager(tmp_path), user_manager=UserMemoryManager(tmp_path), max_tokens=10)
    # System message that uses all 10 tokens
    history = [
        {"role": "system", "content": "abcdefghij"},  # ~2-3 tokens with tiktoken
        {"role": "user", "content": "Hello"},
    ]
    window = strategy.get_context_window(history)
    # System message should always be present
    assert any(m.get("role") == "system" for m in window)


# --- Corrupt session file recovery ---


def test_corrupt_session_file_falls_back_to_empty(tmp_path):
    """MemoryStorage should recover gracefully when session file is corrupted.

    SessionManager.load_session raises ValueError for structurally corrupt
    files (e.g. top-level value is not a list). MemoryStorage must catch that
    and fall back to an empty message list instead of crashing.
    """
    import uuid

    sm = SessionManager(tmp_path)
    sid = str(uuid.uuid4())
    session_path = tmp_path / "sessions" / f"session-{sid}.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    # Write structurally corrupt JSON (dict instead of list)
    session_path.write_text('{"corrupt": true}', encoding="utf-8")

    # Should NOT raise ValueError; should fall back to empty
    storage = MemoryStorage(session_manager=sm, session_id=sid)
    assert storage.get_history() == []

    # Should still be able to add messages and save
    storage.add_message("user", "hello")
    assert len(storage.get_history()) == 1


def test_corrupt_session_file_is_quarantined(tmp_path, caplog):
    """Corrupt session file should be renamed to .corrupt, not silently dropped.

    When MemoryStorage detects a corrupt session (ValueError from load_session),
    it must quarantine the file by renaming it to session-<id>.json.corrupt.
    This preserves the corrupt data for potential recovery.
    """
    import uuid
    import logging

    sm = SessionManager(tmp_path)
    sid = str(uuid.uuid4())
    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / f"session-{sid}.json"
    corrupt_path = session_dir / f"session-{sid}.json.corrupt"

    # Write structurally corrupt JSON
    corrupt_data = '{"corrupt": true}'
    session_path.write_text(corrupt_data, encoding="utf-8")

    # Capture log output
    with caplog.at_level(logging.WARNING, logger="memory.storage"):
        storage = MemoryStorage(session_manager=sm, session_id=sid)

    # Corrupt file should have been renamed to .corrupt
    assert corrupt_path.exists(), "Corrupt file should be quarantined as .corrupt"
    assert not session_path.exists(), "Original corrupt file should be renamed away"
    assert corrupt_path.read_text(encoding="utf-8") == corrupt_data

    # Should log a warning
    assert any("corrupt" in record.message.lower() or "quarantine" in record.message.lower()
               for record in caplog.records)

    # Storage should work normally with empty messages
    assert storage.get_history() == []
    storage.add_message("user", "hello")
    storage.save()

    # save() should write a fresh (non-corrupt) file at the original path
    assert session_path.exists(), "save() should write a fresh session file"
    saved = sm.load_session(sid)
    assert len(saved) == 1
    assert saved[0]["role"] == "user"


# --- Quarantine defense-in-depth ---


def test_quarantine_rejects_invalid_session_id(tmp_path, caplog):
    """_quarantine_corrupt_file should reject non-UUID session_ids.

    Defense-in-depth: even though load_session validates UUID before raising
    ValueError, the quarantine function must also validate to prevent
    path traversal via crafted session_id strings.
    """
    sm = SessionManager(tmp_path)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Malicious session_id that could traverse directories
    malicious_id = "../../etc/passwd"

    # Create a file that looks like the "corrupt" target to prove quarantine did NOT run
    # (If quarantine ran with the malicious id, it would try to rename outside sessions dir)
    with caplog.at_level(logging.WARNING, logger="memory.storage"):
        MemoryStorage._quarantine_corrupt_file(sm, malicious_id)

    # Should log a warning about invalid session_id, not attempt rename
    assert any("invalid" in record.message.lower() or "skip" in record.message.lower()
               for record in caplog.records), \
        f"Expected warning about invalid session_id, got: {[r.message for r in caplog.records]}"

    # No files should have been created or renamed in the sessions directory
    quarantined_files = list(sessions_dir.glob("*.corrupt"))
    assert quarantined_files == [], \
        f"No files should be quarantined for invalid session_id, found: {quarantined_files}"


def test_quarantine_rejects_path_traversal(tmp_path, caplog):
    """_quarantine_corrupt_file should reject session_ids with path traversal.

    A session_id like '../foo' is not a valid UUID and must be rejected.
    The resolved path must stay within the sessions directory.
    """
    sm = SessionManager(tmp_path)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    traversal_id = "../../../tmp/evil"

    with caplog.at_level(logging.WARNING, logger="memory.storage"):
        MemoryStorage._quarantine_corrupt_file(sm, traversal_id)

    # Should log warning, not crash or rename files outside sessions dir
    assert len(caplog.records) >= 1, "Expected at least one warning log"

    # Verify sessions directory is clean
    quarantined_files = list(sessions_dir.glob("*.corrupt"))
    assert quarantined_files == []


def test_quarantine_accepts_valid_uuid(tmp_path, caplog):
    """_quarantine_corrupt_file should work normally for valid UUIDs.

    This ensures the validation fix doesn't break the happy path.
    """
    import uuid

    sm = SessionManager(tmp_path)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    valid_id = str(uuid.uuid4())
    session_path = sessions_dir / f"session-{valid_id}.json"
    corrupt_path = sessions_dir / f"session-{valid_id}.json.corrupt"

    # Create a corrupt file to quarantine
    session_path.write_text('{"corrupt": true}', encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="memory.storage"):
        MemoryStorage._quarantine_corrupt_file(sm, valid_id)

    # File should be renamed to .corrupt
    assert corrupt_path.exists(), "Valid UUID should be quarantined"
    assert not session_path.exists(), "Original file should be renamed"
    assert corrupt_path.read_text(encoding="utf-8") == '{"corrupt": true}'


def test_quarantine_rejects_empty_string(tmp_path, caplog):
    """_quarantine_corrupt_file should reject empty string session_id."""
    sm = SessionManager(tmp_path)
    (tmp_path / "sessions").mkdir(parents=True, exist_ok=True)

    with caplog.at_level(logging.WARNING, logger="memory.storage"):
        MemoryStorage._quarantine_corrupt_file(sm, "")

    assert len(caplog.records) >= 1
    quarantined_files = list((tmp_path / "sessions").glob("*.corrupt"))
    assert quarantined_files == []


# --- Quality Review: resume_session ---

def test_resume_session_switches_active_session(tmp_path):
    """resume_session() 应切换当前活跃会话并加载其消息。

    验证：
    1. resume 后 add_message 写入的是被恢复的会话，而非旧会话。
    2. save + load 能读回 resume 后写入的消息。
    """
    from memory.provider import BrixMemoryProvider

    provider = BrixMemoryProvider(data_dir=tmp_path, max_context_tokens=8000)
    # 当前会话写一些消息
    provider.add_message("user", "first session msg")
    provider.save_session()
    first_sid = provider._current_session_id

    # 创建第二个会话并写消息
    second_sid = provider.create_session()
    provider.add_message("user", "second session msg")
    provider.save_session()

    # 恢复第一个会话
    messages = provider.resume_session(first_sid)
    assert len(messages) == 1
    assert messages[0]["content"] == "first session msg"

    # resume 后 add_message 应写入第一个会话
    provider.add_message("user", "resumed msg")
    provider.save_session()

    # 验证第一个会话现在有 2 条消息
    reloaded = provider.load_session(first_sid)
    assert len(reloaded) == 2
    assert reloaded[1]["content"] == "resumed msg"

    # 第二个会话不受影响
    second_msgs = provider.load_session(second_sid)
    assert len(second_msgs) == 1
    assert second_msgs[0]["content"] == "second session msg"


def test_empty_session_cleaned_up_on_new_session(tmp_path):
    """空 session 在创建新 session 时应被自动清理。"""
    from memory.provider import BrixMemoryProvider

    provider = BrixMemoryProvider(data_dir=tmp_path, max_context_tokens=8000)
    empty_sid = provider.create_session()
    # 切换到另一个会话 — 空 session 应被清理
    provider.create_session()
    # 空 session 已从索引移除，resume 应抛出异常
    with pytest.raises(FileNotFoundError):
        provider.resume_session(empty_sid)


def test_non_empty_session_preserved_on_new_session(tmp_path):
    """有消息的 session 在创建新 session 时不应被清理。"""
    from memory.provider import BrixMemoryProvider

    provider = BrixMemoryProvider(data_dir=tmp_path, max_context_tokens=8000)
    sid = provider.create_session()
    provider.add_message("user", "hello")
    provider.save_session()  # 持久化到磁盘
    # 切换到另一个会话 — 有消息的 session 应保留
    provider.create_session()
    messages = provider.resume_session(sid)
    assert len(messages) == 1
    assert messages[0]["content"] == "hello"


def test_resume_session_raises_for_nonexistent(tmp_path):
    """resume_session() 对不存在的 session_id 应抛出异常。"""
    import uuid
    from memory.provider import BrixMemoryProvider

    provider = BrixMemoryProvider(data_dir=tmp_path, max_context_tokens=8000)
    with pytest.raises(FileNotFoundError):
        provider.resume_session(str(uuid.uuid4()))


def test_resume_session_in_protocol():
    """MemoryProvider Protocol 应包含 resume_session 方法。"""
    from memory import MemoryProvider
    assert hasattr(MemoryProvider, "resume_session")


# --- Quality Review: factory default data_dir ---

def test_factory_default_data_dir_uses_dotbrix(tmp_path, monkeypatch):
    """create_memory_provider() 默认 data_dir 应为 CWD/.brix/data，而非包内目录。"""
    from memory import create_memory_provider
    monkeypatch.chdir(tmp_path)
    provider = create_memory_provider()
    # 验证 data_dir 是 tmp_path/.brix/data
    assert provider._data_dir == tmp_path / ".brix" / "data"
    assert provider._data_dir.exists()


def test_factory_explicit_data_dir_overrides_default(tmp_path):
    """显式传入 data_dir 时应忽略默认值。"""
    from memory import create_memory_provider
    custom = tmp_path / "custom"
    provider = create_memory_provider(data_dir=custom)
    assert provider._data_dir == custom


def test_factory_default_raises_if_data_dir_not_writable(tmp_path, monkeypatch):
    """当 CWD/.brix 无法创建（只读文件系统）时，应抛出明确的错误。"""
    import os
    from memory import create_memory_provider

    # 创建一个只读目录作为 CWD
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    readonly_dir.chmod(0o555)  # r-xr-xr-x 可以 chdir 但不能写
    monkeypatch.chdir(readonly_dir)
    # monkeypatch 会在测试结束时恢复 CWD

    with pytest.raises((OSError, PermissionError)):
        create_memory_provider()

    # 恢复权限以便清理
    readonly_dir.chmod(0o755)
