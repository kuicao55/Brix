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


def test_single_char_cjk_query_finds_match():
    """单字 CJK 查询（如"辣"）不应被过滤。"""
    from memory.searcher import KeywordMemorySearcher
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        ltm.write_topic("food.md", "## 食物偏好\n- 喜欢辣的食物",
                        {"name": "食物偏好", "description": "用户的食物偏好", "type": "user"})
        ltm.update_index()
        searcher = KeywordMemorySearcher(ltm, short_term=None)
        results = searcher.search("辣")
        assert len(results) > 0
        assert "辣" in results[0].content


def test_malformed_long_term_topic_skipped():
    """长期记忆数据损坏时应跳过该条目，而非崩溃。"""
    from memory.searcher import KeywordMemorySearcher

    class FakeLongTerm:
        """模拟损坏的长期记忆：list_topics 返回缺少 'file' 键的条目。"""
        def list_topics(self):
            return [
                {"file": "good.md"},  # 正常
                {"bad_key": "no_file"},  # 缺少 file
                "not_a_dict",  # 类型错误
            ]

        def read_topic(self, filename):
            if filename == "good.md":
                return "包含关键词的正常内容"
            raise FileNotFoundError(f"{filename} not found")

    searcher = KeywordMemorySearcher(FakeLongTerm(), short_term=None)
    results = searcher.search("关键词")
    assert len(results) == 1
    assert results[0].topic == "good.md"


def test_malformed_short_term_item_skipped():
    """短期记忆数据损坏时应跳过该条目，而非崩溃。"""
    from memory.searcher import KeywordMemorySearcher

    class FakeShortTerm:
        """模拟损坏的短期记忆：get_recent 返回非字符串 content。"""
        def get_recent(self, limit=100):
            return [
                {"content": "正常的关键词内容"},
                {"content": 12345},  # content 非字符串
                {"wrong_key": "no content key"},  # 缺少 content
                "not_a_dict",  # 类型错误
                {"content": None},  # content 为 None
            ]

    searcher = KeywordMemorySearcher(long_term=None, short_term=FakeShortTerm())
    results = searcher.search("关键词")
    assert len(results) == 1
    assert "关键词" in results[0].content


def test_repeated_keywords_not_inflated():
    """重复关键词不应导致分数膨胀。"""
    from memory.searcher import KeywordMemorySearcher

    # 直接测试 _extract_keywords 去重
    keywords = KeywordMemorySearcher._extract_keywords("辣 辣 辣")
    assert len(keywords) == 1
    assert keywords[0] == "辣"

    # 测试搜索行为：重复查询词不应比单次查询得分更高
    class FakeLongTerm:
        def list_topics(self):
            return [{"file": "test.md"}]
        def read_topic(self, filename):
            return "辣的食物很好吃"

    searcher = KeywordMemorySearcher(FakeLongTerm(), short_term=None)
    results_single = searcher.search("辣")
    results_repeated = searcher.search("辣 辣 辣")
    assert len(results_single) > 0
    assert len(results_repeated) > 0
    assert results_single[0].relevance == results_repeated[0].relevance
