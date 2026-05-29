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


def test_path_traversal_rejected():
    """session_id 含路径遍历字符时应拒绝。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        with pytest.raises(ValueError, match="非法 session_id"):
            stm.add_item("../../etc/passwd", "hack", "test")
        with pytest.raises(ValueError, match="非法 session_id"):
            stm.get_by_session("../escape")
        with pytest.raises(ValueError, match="非法 session_id"):
            stm.cleanup_sessions(["../../tmp/evil"])


# --- Issue 3: 并发写入竞态条件 ---

def test_add_item_concurrent_no_lost_items():
    """Issue 3: 并发调用 add_item 不应丢失任何 item。"""
    import threading
    from memory.short_term import ShortTermMemory

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        errors = []
        num_threads = 10
        items_per_thread = 20

        def add_items(thread_id):
            try:
                for i in range(items_per_thread):
                    stm.add_item("sess-concurrent", f"item-{thread_id}-{i}", "test")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_items, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发写入时出错: {errors}"
        items = stm.get_by_session("sess-concurrent")
        expected = num_threads * items_per_thread
        assert len(items) == expected, \
            f"并发写入应有 {expected} 个 items，实际只有 {len(items)} 个（丢失了 {expected - len(items)} 个）"


# --- Issue 4: 损坏的 session 文件导致静默覆盖 ---

def test_corrupted_session_file_is_quarantined():
    """Issue 4: 损坏的 session 文件应被隔离（重命名为 .corrupt），而非被覆盖。"""
    from memory.short_term import ShortTermMemory

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        session_dir = Path(d) / "short-term"
        session_dir.mkdir(parents=True, exist_ok=True)

        # 写入一个损坏的 JSON 文件
        bad_file = session_dir / "corrupt-sess.json"
        bad_file.write_text("{invalid json content", encoding="utf-8")

        # add_item 应该不崩溃，且损坏文件被隔离
        stm.add_item("corrupt-sess", "new item", "test")

        # 损坏的文件应被重命名为 .corrupt
        quarantined = session_dir / "corrupt-sess.json.corrupt"
        assert quarantined.exists(), \
            "损坏的 session 文件应被重命名为 .corrupt 文件"

        # 原始文件应为新内容（只含新 item）
        original = session_dir / "corrupt-sess.json"
        assert original.exists(), "应创建新的 session 文件"
        data = json.loads(original.read_text(encoding="utf-8"))
        assert len(data["items"]) == 1, \
            f"新文件应只含 1 个 item，实际有 {len(data['items'])} 个"
        assert data["items"][0]["content"] == "new item"


def test_corrupted_session_file_preserved_for_inspection():
    """Issue 4: 隔离的损坏文件应保留原始内容，方便排查。"""
    from memory.short_term import ShortTermMemory

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        session_dir = Path(d) / "short-term"
        session_dir.mkdir(parents=True, exist_ok=True)

        # 写入损坏的 JSON 文件
        bad_content = '{"items": [partial...'
        bad_file = session_dir / "inspect-sess.json"
        bad_file.write_text(bad_content, encoding="utf-8")

        stm.add_item("inspect-sess", "replacement", "test")

        # 隔离文件的内容应与原始损坏内容一致
        quarantined = session_dir / "inspect-sess.json.corrupt"
        assert quarantined.read_text(encoding="utf-8") == bad_content, \
            "隔离文件应保留原始损坏内容，方便排查"
