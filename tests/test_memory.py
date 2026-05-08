"""Tests for the memory storage and strategy (Task 5).

TDD: These tests are written BEFORE the implementation.
Step 2 (RED): all should fail with ModuleNotFoundError.
Step 4 (GREEN): all should pass after implementation.
"""

import json
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
