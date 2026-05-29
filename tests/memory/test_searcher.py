import pytest
from pathlib import Path
import tempfile


def test_keyword_search_finds_match():
    """关键词搜索应找到匹配的长期记忆。"""
    from memory.searcher import KeywordMemorySearcher
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        ltm.write_topic("food.md", "## 食物偏好\n- 喜欢辣的食物\n- 会做爆炒腊肉",
                        {"name": "食物偏好", "description": "用户的食物偏好", "type": "user"})
        ltm.update_index()
        searcher = KeywordMemorySearcher(ltm, short_term=None)
        results = searcher.search("辣的食物")
        assert len(results) > 0
        assert "辣" in results[0].content


def test_keyword_search_returns_empty_for_no_match():
    """无匹配时应返回空列表。"""
    from memory.searcher import KeywordMemorySearcher
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        searcher = KeywordMemorySearcher(ltm, short_term=None)
        results = searcher.search("完全无关的关键词")
        assert results == []


def test_search_includes_short_term():
    """搜索应同时覆盖短期记忆。"""
    from memory.searcher import KeywordMemorySearcher
    from memory.long_term import LongTermMemory
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        stm = ShortTermMemory(Path(d))
        stm.add_item("sess-1", "用户喜欢吃火锅", "pref_detection")
        searcher = KeywordMemorySearcher(ltm, short_term=stm)
        results = searcher.search("火锅")
        assert any("火锅" in r.content for r in results)
