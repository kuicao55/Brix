import os
import pytest
from contextlib import contextmanager
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
    """list_topics 应返回 MEMORY.md 中的索引（仅 CATEGORY_FILES）。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        ltm.write_topic("user.md", "内容1", {"name": "主题1", "description": "描述1", "type": "long_term"})
        ltm.write_topic("work.md", "内容2", {"name": "主题2", "description": "描述2", "type": "long_term"})
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


# ============================================================
# CQR Fix Tests
# ============================================================


def test_append_dedup_not_substring_match():
    """Issue 1: 去重应使用行级精确匹配，而非子串匹配。
    如果已有内容 '用户喜欢中餐和西餐'，追加 '用户喜欢中餐' 应被允许。
    当前 bug：'用户喜欢中餐' 是 '用户喜欢中餐和西餐' 的子串，会被错误去重。
    修复后应出现两行（行级去重不误判子串）。
    """
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "用户画像", "description": "描述", "type": "long_term"}
        ltm.write_topic("user.md", "用户喜欢中餐和西餐", fm, append=True)
        ltm.write_topic("user.md", "用户喜欢中餐", fm, append=True)
        body = ltm._extract_body(ltm.read_topic("user.md"))
        lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
        # 行级去重后应有两条不同的事实
        assert len(lines) == 2, f"期望 2 行，实际 {len(lines)} 行: {lines}"
        assert "用户喜欢中餐和西餐" in lines
        assert "用户喜欢中餐" in lines


def test_append_dedup_exact_line_match_still_works():
    """Issue 1: 行级精确去重 — 完全相同的行应被去重。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "用户画像", "description": "描述", "type": "long_term"}
        ltm.write_topic("user.md", "用户喜欢中餐", fm, append=True)
        ltm.write_topic("user.md", "用户喜欢中餐", fm, append=True)
        body = ltm._extract_body(ltm.read_topic("user.md"))
        # 精确重复的行应只出现一次
        lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
        assert lines.count("用户喜欢中餐") == 1


def test_append_dedup_exact_line_with_whitespace_still_works():
    """Issue 1: 行级去重应 strip 比较。"""
    from memory.long_term import LongTermMemory
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "用户画像", "description": "描述", "type": "long_term"}
        ltm.write_topic("user.md", "  用户喜欢中餐  ", fm, append=True)
        ltm.write_topic("user.md", "用户喜欢中餐", fm, append=True)
        body = ltm._extract_body(ltm.read_topic("user.md"))
        lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
        assert lines.count("用户喜欢中餐") == 1


def test_append_uses_file_lock():
    """Issue 2: 追加模式应使用文件锁保护读-去重-写流程。
    验证 _file_lock 被调用。
    """
    from memory.long_term import LongTermMemory
    from unittest.mock import patch, MagicMock
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "测试", "description": "描述", "type": "long_term"}
        ltm.write_topic("user.md", "第一行", fm, append=True)

        # 检查 write_topic 在 append 模式下是否创建了 lock 文件
        lock_path = (ltm._dir / "user.md.lock")
        # 当前实现没有锁，lock 文件不应存在
        # 修复后，lock 文件应该在 append 操作期间被创建
        # 我们通过检查 _file_lock 是否被调用来验证
        with patch.object(ltm, '_file_lock', wraps=ltm._file_lock) as mock_lock:
            ltm.write_topic("user.md", "第二行", fm, append=True)
            mock_lock.assert_called()


def test_append_file_lock_covers_read_and_write():
    """Issue 2: 文件锁应覆盖完整的读-去重-写关键区域。
    通过 monkeypatch 验证锁被正确使用。
    """
    from memory.long_term import LongTermMemory
    import fcntl
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "测试", "description": "描述", "type": "long_term"}
        ltm.write_topic("user.md", "第一行", fm, append=True)

        flock_calls = []
        original_flock = fcntl.flock

        def tracking_flock(fd, operation):
            flock_calls.append(operation)
            return original_flock(fd, operation)

        import unittest.mock
        with unittest.mock.patch('fcntl.flock', side_effect=tracking_flock):
            ltm.write_topic("user.md", "第二行", fm, append=True)
        # 应该有 LOCK_EX 和 LOCK_UN 两次调用
        assert fcntl.LOCK_EX in flock_calls
        assert fcntl.LOCK_UN in flock_calls


def test_frontmatter_parsing_with_delimiter_in_value():
    """Issue 3: frontmatter 值中包含 '---' 时不应提前终止解析。
    当前 bug：text.find("---", 3) 会匹配值中的 '---'，导致解析截断。
    """
    from memory.long_term import LongTermMemory
    # frontmatter 值中包含 '---'
    text = "---\ntest: a---b\n---\nbody\n"
    fm = LongTermMemory._parse_frontmatter(text)
    # frontmatter 应完整解析，test 的值应为 'a---b'
    assert fm.get("test") == "a---b", f"期望 'a---b'，实际 '{fm.get('test')}'"


def test_frontmatter_parsing_with_triple_dash_in_content():
    """Issue 3: body 中独立的 '---' 行不应终止 frontmatter 解析。"""
    from memory.long_term import LongTermMemory

    # 测试一个内容中包含 '---' 的完整文件
    text = "---\nname: 测试\ntype: user\n---\n\n## 标题\n\n一些内容\n\n---\n\n更多内容\n"
    fm = LongTermMemory._parse_frontmatter(text)
    assert fm.get("name") == "测试"
    assert fm.get("type") == "user"

    body = LongTermMemory._extract_body(text)
    # body 应包含分隔线之后的全部内容
    assert "更多内容" in body


def test_extract_body_with_delimiter_in_content():
    """Issue 3: _extract_body 应正确提取含 '---' 的 body。"""
    from memory.long_term import LongTermMemory

    text = "---\nname: 测试\n---\n\n正文第一行\n---\n正文第二行\n"
    body = LongTermMemory._extract_body(text)
    assert "正文第一行" in body
    assert "正文第二行" in body


def test_update_index_includes_non_category_topic_files():
    """update_index 应索引所有 *.md 文件（除 MEMORY.md），包括非分类 topic 文件。
    修复 Issue 3 后，dream.py 等模块写入的 topic 文件也会被索引。
    """
    from memory.long_term import LongTermMemory, CATEGORY_FILES
    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "测试", "description": "描述", "type": "long_term"}
        # 写入一个分类文件
        ltm.write_topic("user.md", "用户内容", fm)
        # 写入一个非分类文件
        ltm.write_topic("custom.md", "自定义内容", fm)
        ltm.update_index()
        topics = ltm.list_topics()
        indexed_files = {t["file"] for t in topics}
        # 分类文件应在索引中
        assert "user.md" in indexed_files
        # 非分类文件也应在索引中（修复后行为）
        assert "custom.md" in indexed_files
        # MEMORY.md 不应在索引中
        assert "MEMORY.md" not in indexed_files


# ============================================================
# CQR Round 2 Fix Tests
# ============================================================


def test_cqr2_lock_covers_write_and_replace():
    """Issue 1 (CRITICAL): append 锁必须覆盖 temp write + os.replace 阶段。
    验证 os.replace 在 _file_lock 上下文内被调用，而非锁外。
    """
    from memory.long_term import LongTermMemory
    import unittest.mock

    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "测试", "description": "描述", "type": "long_term"}
        # 先创建文件
        ltm.write_topic("user.md", "初始内容", fm, append=True)

        # 追踪 os.replace 调用时锁是否仍持有
        lock_is_held = False
        replace_called_inside_lock = []

        original_file_lock = ltm._file_lock

        @contextmanager
        def tracking_file_lock(path, exclusive=True):
            nonlocal lock_is_held
            lock_is_held = True
            try:
                with original_file_lock(path, exclusive):
                    yield
            finally:
                lock_is_held = False

        original_replace = os.replace

        def tracking_replace(src, dst):
            replace_called_inside_lock.append(lock_is_held)
            return original_replace(src, dst)

        with unittest.mock.patch.object(ltm, '_file_lock', tracking_file_lock), \
             unittest.mock.patch('os.replace', side_effect=tracking_replace):
            ltm.write_topic("user.md", "追加内容", fm, append=True)

        assert len(replace_called_inside_lock) == 1, "os.replace 应被调用一次"
        assert replace_called_inside_lock[0] is True, \
            "os.replace 必须在 _file_lock 持有期间调用（当前在锁外调用）"


def test_cqr2_append_on_missing_file_uses_lock():
    """Issue 2 (HIGH): append=True 且文件不存在时，仍应使用文件锁。
    两个 writer 竞争创建新文件时，必须有锁保护。
    """
    from memory.long_term import LongTermMemory
    import unittest.mock

    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "测试", "description": "描述", "type": "long_term"}

        # 追踪 _file_lock 是否被调用
        lock_called = False
        original_file_lock = ltm._file_lock

        @contextmanager
        def tracking_file_lock(path, exclusive=True):
            nonlocal lock_called
            lock_called = True
            with original_file_lock(path, exclusive):
                yield

        with unittest.mock.patch.object(ltm, '_file_lock', tracking_file_lock):
            # 文件不存在时 append
            ltm.write_topic("user.md", "第一条", fm, append=True)

        assert lock_called, "append=True 且文件不存在时，_file_lock 应被调用"


def test_cqr2_update_index_includes_topic_files():
    """Issue 3 (HIGH): update_index 应索引 CATEGORY_FILES + 其他 topic 文件。
    dream.py 等模块仍写入非分类 topic 文件，这些文件不能从索引中消失。
    """
    from memory.long_term import LongTermMemory

    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "测试", "description": "描述", "type": "long_term"}
        # 写入分类文件
        ltm.write_topic("user.md", "用户内容", fm)
        # 写入非分类 topic 文件（模拟 dream.py 写入）
        ltm.write_topic("dream_insights.md", "Dream 内容", fm)
        ltm.write_topic("custom_topic.md", "自定义内容", fm)
        ltm.update_index()

        topics = ltm.list_topics()
        indexed_files = {t["file"] for t in topics}
        # 分类文件应在索引中
        assert "user.md" in indexed_files
        # 非分类 topic 文件也应在索引中
        assert "dream_insights.md" in indexed_files, \
            "非分类 topic 文件（如 dream 写入的文件）应被索引"
        assert "custom_topic.md" in indexed_files, \
            "非分类 topic 文件应被索引"


def test_cqr2_multiline_content_dedup():
    """Issue 4 (MEDIUM): 多行 payload 的行级去重应正确工作。
    当前 bug：content.strip() 是整个多行字符串，与单行集合比较永远不匹配。
    """
    from memory.long_term import LongTermMemory

    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "测试", "description": "描述", "type": "long_term"}

        multiline = "第一行\n第二行\n第三行"
        ltm.write_topic("user.md", multiline, fm, append=True)
        # 再次追加相同多行内容
        ltm.write_topic("user.md", multiline, fm, append=True)

        content = ltm.read_topic("user.md")
        body = ltm._extract_body(content)
        # 多行内容去重后应只出现一次
        count = body.count("第一行")
        assert count == 1, f"多行内容应去重，'第一行' 出现 {count} 次"


def test_cqr2_multiline_partial_overlap_not_deduped():
    """Issue 4 (MEDIUM): 多行 payload 中部分行重复不应整块去重。
    如果已有 ['第一行', '第二行']，追加 ['第二行', '第三行'] 只应跳过已有的行。
    """
    from memory.long_term import LongTermMemory

    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        fm = {"name": "测试", "description": "描述", "type": "long_term"}

        ltm.write_topic("user.md", "第一行\n第二行", fm, append=True)
        ltm.write_topic("user.md", "第二行\n第三行", fm, append=True)

        content = ltm.read_topic("user.md")
        body = ltm._extract_body(content)
        lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
        # 应有 3 行（第一行、第二行、第三行），第二行不重复
        assert "第一行" in lines
        assert "第二行" in lines
        assert "第三行" in lines
        assert lines.count("第二行") == 1, \
            f"'第二行' 应去重，出现 {lines.count('第二行')} 次"
