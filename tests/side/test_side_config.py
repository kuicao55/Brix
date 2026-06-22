"""Side 配置测试。"""
from __future__ import annotations

import pytest

from config.loader import load_config


def test_config_has_side_block():
    config = load_config()
    assert "side" in config
    assert "enabled" in config["side"]
    assert "model" in config["side"]
    assert "tasks" in config["side"]


def test_config_routing_simplified():
    config = load_config()
    routing = config.get("routing", {})
    assert "default_model" in routing
    assert "fallback_model" in routing
    assert "chat_model" not in routing
    assert "intent_model" not in routing


def test_config_side_tasks_structure():
    config = load_config()
    tasks = config["side"]["tasks"]
    expected_tasks = [
        "session_title",
        "tool_summary",
        "history_search",
        "context_compress",
        "session_summary",
    ]
    for task_name in expected_tasks:
        assert task_name in tasks, f"Missing task config: {task_name}"
        assert "enabled" in tasks[task_name], f"Missing enabled flag for {task_name}"
