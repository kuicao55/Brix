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


def test_memory_strategy_should_save():
    strategy = MemoryStrategy()
    assert strategy.should_save({"role": "user", "content": "hello"}) is True


def test_memory_strategy_context_window():
    strategy = MemoryStrategy()
    history = [{"role": "user", "content": f"message {i}"} for i in range(100)]
    # Each "message N" is ~3 tokens; 100 messages = ~300 tokens
    # Use limit of 100 to force truncation
    window = strategy.get_context_window(history, max_tokens=100)
    assert len(window) < len(history)
    assert len(window) > 0


def test_token_counting_truncation():
    """MemoryStrategy should truncate by tokens, not characters."""
    strategy = MemoryStrategy(max_tokens=50)  # very small limit

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


def test_system_message_preservation():
    """System messages should always be preserved."""
    strategy = MemoryStrategy(max_tokens=10)

    history = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello " * 100},  # large message to push over limit
    ]

    window = strategy.get_context_window(history)
    # System message should always be in the window
    assert any(m.get("role") == "system" for m in window)


def test_graceful_fallback_without_tiktoken():
    """Should fall back to char-based counting if tiktoken fails."""
    strategy = MemoryStrategy(max_tokens=4000)

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


def test_count_tokens_none_content():
    """_count_tokens should return 0 for None or empty content, not crash."""
    strategy = MemoryStrategy()
    assert strategy._count_tokens("") == 0
    assert strategy._count_tokens(None) == 0


def test_count_tokens_none_content_fallback():
    """_count_tokens with char-based fallback should also handle None/empty."""
    strategy = MemoryStrategy()
    strategy._encoder = None  # force char-based fallback
    assert strategy._count_tokens("") == 0
    assert strategy._count_tokens(None) == 0


def test_context_window_none_content_messages():
    """Messages with content=None (e.g. tool-call messages) should not crash."""
    strategy = MemoryStrategy(max_tokens=1000)
    history = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": None, "tool_calls": [{"name": "foo"}]},
        {"role": "user", "content": "Continue"},
    ]
    window = strategy.get_context_window(history)
    assert len(window) == 4  # all fit within 1000 tokens


def test_context_window_system_exceeds_budget():
    """If system messages alone exceed the token limit, truncate to fit."""
    strategy = MemoryStrategy(max_tokens=5)
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


def test_context_window_system_exceeds_budget_exact_boundary():
    """Edge case: system messages exactly at the budget boundary."""
    strategy = MemoryStrategy(max_tokens=10)
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
