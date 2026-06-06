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


# ============================================================
# Task 2: 按大分类改造测试
# ============================================================


def test_category_files_constant():
    """CATEGORY_FILES 应包含四个分类文件名。"""
    from memory.long_term import LongTermMemory, CATEGORY_FILES
    assert CATEGORY_FILES == {"user.md", "knowledge.md", "work.md", "history.md"}


def test_write_topic_append_creates_new_file():
    """append=True 时，文件不存在应创建新文件（含 frontmatter + 内容）。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        ltm.write_topic(
            "user.md", "用户喜欢中餐",
            {"name": "用户画像", "description": "用户核心信息", "type": "long_term"},
            append=True,
        )
        content = ltm.read_topic("user.md")
        assert "用户喜欢中餐" in content
        assert "---" in content
        assert "name: 用户画像" in content


def test_write_topic_append_adds_to_existing():
    """append=True 时，已有文件应追加内容，不覆盖旧内容。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "用户画像", "description": "用户核心信息", "type": "long_term"}
        ltm.write_topic("user.md", "用户喜欢中餐", fm, append=True)
        ltm.write_topic("user.md", "用户在家办公", fm, append=True)
        content = ltm.read_topic("user.md")
        assert "用户喜欢中餐" in content
        assert "用户在家办公" in content


def test_write_topic_append_dedup():
    """append=True 时，重复内容不应被追加。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "用户画像", "description": "用户核心信息", "type": "long_term"}
        ltm.write_topic("user.md", "用户喜欢中餐", fm, append=True)
        ltm.write_topic("user.md", "用户喜欢中餐", fm, append=True)
        content = ltm.read_topic("user.md")
        # 内容只应出现一次（在 frontmatter 之后的 body 中）
        body = content.split("---", 2)[-1] if content.count("---") >= 2 else content
        assert body.count("用户喜欢中餐") == 1


def test_write_topic_append_dedup_with_whitespace():
    """append=True 时，仅空白差异的内容应被去重。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "用户画像", "description": "用户核心信息", "type": "long_term"}
        ltm.write_topic("user.md", "  用户喜欢中餐  \n", fm, append=True)
        ltm.write_topic("user.md", "用户喜欢中餐", fm, append=True)
        content = ltm.read_topic("user.md")
        body = content.split("---", 2)[-1] if content.count("---") >= 2 else content
        # 去重后只应出现一次
        assert body.strip().count("用户喜欢中餐") == 1


def test_write_topic_overwrite_default():
    """append=False（默认）时，应覆盖写入。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "用户画像", "description": "用户核心信息", "type": "long_term"}
        ltm.write_topic("user.md", "旧内容", fm)
        ltm.write_topic("user.md", "新内容", fm)
        content = ltm.read_topic("user.md")
        assert "新内容" in content
        assert "旧内容" not in content


def test_update_index_reflects_category_files():
    """update_index 应从分类文件重建索引。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm_user = {"name": "用户画像", "description": "用户核心信息", "type": "long_term"}
        fm_work = {"name": "工作上下文", "description": "用户工作相关", "type": "long_term"}
        ltm.write_topic("user.md", "用户喜欢中餐", fm_user)
        ltm.write_topic("work.md", "用户是开发者", fm_work)
        ltm.update_index()
        topics = ltm.list_topics()
        names = [t["name"] for t in topics]
        assert "用户画像" in names
        assert "工作上下文" in names
        assert len(topics) == 2


def test_update_index_includes_all_category_files():
    """update_index 应包含所有存在的分类文件。"""
    from memory.long_term import LongTermMemory, CATEGORY_FILES
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "测试", "description": "测试文件", "type": "long_term"}
        for cat_file in CATEGORY_FILES:
            ltm.write_topic(cat_file, f"内容_{cat_file}", fm)
        ltm.update_index()
        topics = ltm.list_topics()
        indexed_files = {t["file"] for t in topics}
        for cat_file in CATEGORY_FILES:
            assert cat_file in indexed_files, f"{cat_file} 不在索引中"


def test_frontmatter_type_long_term():
    """frontmatter 中 type 应为 long_term。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        ltm.write_topic(
            "user.md", "测试内容",
            {"name": "用户画像", "description": "用户核心信息", "type": "long_term"},
        )
        content = ltm.read_topic("user.md")
        fm = LongTermMemory._parse_frontmatter(content)
        assert fm["type"] == "long_term"
        assert fm["name"] == "用户画像"
        assert fm["description"] == "用户核心信息"


def test_write_topic_non_category_still_works():
    """非分类文件的 topic 写入应保持向后兼容。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        ltm.write_topic("custom_topic.md", "自定义内容", {"name": "自定义", "description": "测试"})
        content = ltm.read_topic("custom_topic.md")
        assert "自定义内容" in content


def test_append_preserves_existing_frontmatter():
    """追加模式应保留已有文件的 frontmatter。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "用户画像", "description": "用户核心信息", "type": "long_term"}
        ltm.write_topic("user.md", "第一条", fm, append=True)
        ltm.write_topic("user.md", "第二条", fm, append=True)
        content = ltm.read_topic("user.md")
        parsed = LongTermMemory._parse_frontmatter(content)
        assert parsed["name"] == "用户画像"
        assert parsed["type"] == "long_term"
