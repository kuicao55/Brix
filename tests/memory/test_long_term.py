import pytest
from pathlib import Path
import tempfile


def test_write_and_read_topic():
    """write_topic 后 read_topic 应返回内容。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        ltm.write_topic("test_topic.md", "## 测试\n- 内容", {"name": "测试", "description": "测试主题", "type": "user"})
        content = ltm.read_topic("test_topic.md")
        assert "测试" in content


def test_list_topics():
    """list_topics 应返回 MEMORY.md 中的索引。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        ltm.write_topic("topic1.md", "内容1", {"name": "主题1", "description": "描述1", "type": "user"})
        ltm.write_topic("topic2.md", "内容2", {"name": "主题2", "description": "描述2", "type": "user"})
        ltm.update_index()
        topics = ltm.list_topics()
        assert len(topics) == 2


def test_remove_topic():
    """remove_topic 应删除文件并更新索引。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        ltm.write_topic("topic1.md", "内容", {"name": "主题", "description": "描述", "type": "user"})
        ltm.remove_topic("topic1.md")
        assert ltm.read_topic("topic1.md") == ""


def test_path_traversal_rejected():
    """topic_file 含路径遍历字符时应拒绝。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        with pytest.raises(ValueError):
            ltm.write_topic("../../etc/passwd", "hack", {"name": "evil"})
        with pytest.raises(ValueError):
            ltm.read_topic("../escape.md")
        with pytest.raises(ValueError):
            ltm.remove_topic("../../tmp/evil.md")


def test_atomic_write_no_corruption():
    """write_topic 应原子写入，内容完整。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        content = "A" * 10000
        ltm.write_topic("big.md", content, {"name": "大文件", "description": "测试原子写入", "type": "user"})
        assert ltm.read_topic("big.md").endswith(content)


def test_list_topics_empty_when_no_index():
    """MEMORY.md 不存在时 list_topics 应返回空列表。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        assert ltm.list_topics() == []


def test_reserved_filename_rejected():
    """MEMORY.md 作为 topic_file 应拒绝。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        with pytest.raises(ValueError, match="保留文件"):
            ltm.write_topic("MEMORY.md", "hack", {"name": "evil"})
        with pytest.raises(ValueError, match="保留文件"):
            ltm.remove_topic("MEMORY.md")
