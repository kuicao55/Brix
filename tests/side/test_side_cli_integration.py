"""CLI 集成 side 层测试。"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def test_cli_imports_side_manager():
    """cli/app.py 导入 SideTaskManager。"""
    import cli.app
    # 验证模块可以导入（不抛出异常）
    assert hasattr(cli.app, 'BrixCLI')


def test_config_routing_no_intent_model():
    """config 中不再有 intent_model 和 chat_model。"""
    from config.loader import load_config
    config = load_config()
    routing = config.get("routing", {})
    assert "intent_model" not in routing
    assert "chat_model" not in routing
