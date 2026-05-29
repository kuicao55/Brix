import pytest
from pathlib import Path
import tempfile
import json

def test_add_and_get_items():
    """add_item 后 get_recent 应返回该 item。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("sess-1", "用户喜欢辣的食物", "pref_detection", "用户说要吃爆炒腊肉")
        items = stm.get_recent(limit=10)
        assert len(items) == 1
        assert items[0]["content"] == "用户喜欢辣的食物"
        assert items[0]["source"] == "pref_detection"

def test_get_by_session():
    """get_by_session 应只返回指定 session 的 items。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("sess-1", "item1", "pref_detection")
        stm.add_item("sess-2", "item2", "pref_detection")
        items = stm.get_by_session("sess-1")
        assert len(items) == 1
        assert items[0]["content"] == "item1"

def test_remove_items():
    """remove_items 应删除指定 id 的 items。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("sess-1", "item1", "pref_detection")
        items = stm.get_recent()
        stm.remove_items([items[0]["id"]])
        assert len(stm.get_recent()) == 0

def test_cleanup_sessions():
    """cleanup_sessions 应删除指定 session 的文件。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("sess-1", "item1", "pref_detection")
        stm.cleanup_sessions(["sess-1"])
        assert len(stm.get_recent()) == 0
