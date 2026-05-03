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
    window = strategy.get_context_window(history, max_chars=500)
    assert len(window) < len(history)
    assert len(window) > 0
