"""Tests for the memory storage and strategy (Task 5).

TDD: These tests are written BEFORE the implementation.
Step 2 (RED): all should fail with ModuleNotFoundError.
Step 4 (GREEN): all should pass after implementation.
"""

import json
import pytest
from memory.storage import MemoryStorage
from memory.strategy import MemoryStrategy


def test_memory_storage_save_and_load(tmp_path):
    path = tmp_path / "memory.json"
    storage = MemoryStorage(path=str(path))
    storage.add_message("user", "hello")
    storage.add_message("assistant", "hi there")
    storage.save()

    storage2 = MemoryStorage(path=str(path))
    history = storage2.get_history()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["content"] == "hi there"


def test_memory_storage_limit(tmp_path):
    path = tmp_path / "memory.json"
    storage = MemoryStorage(path=str(path))
    for i in range(10):
        storage.add_message("user", f"msg {i}")
    storage.save()

    storage2 = MemoryStorage(path=str(path))
    history = storage2.get_history(limit=3)
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
    path = tmp_path / "memory.json"
    # First instance: add messages and save
    storage = MemoryStorage(path=str(path))
    storage.add_message("user", "hello")
    storage.add_message("assistant", "hi there")
    storage.save()

    # Verify messages exist in a fresh instance
    storage2 = MemoryStorage(path=str(path))
    assert len(storage2.get_history()) == 2

    # Clear and save (simulating /clear command)
    storage2.clear()
    storage2.save()

    # "Restart" — new instance should see empty history
    storage3 = MemoryStorage(path=str(path))
    assert len(storage3.get_history()) == 0
