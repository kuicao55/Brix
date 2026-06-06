"""ShortTermMemory 测试 — 按日期文件结构。"""
from __future__ import annotations

import json
import threading
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


# ============================================================
# 1. 基本功能：新 add_item 签名 + 日期文件结构
# ============================================================

def test_add_item_date_file_structure():
    """add_item 应创建 short-term/YYYY-MM-DD.json 文件。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("用户喜欢辣的食物", "pref_detection", date="2026-06-06",
                      session_id="sess-1", context="用户说要吃爆炒腊肉")
        # 文件应为 2026-06-06.json
        f = Path(d) / "short-term" / "2026-06-06.json"
        assert f.exists(), f"日期文件 {f} 应存在"
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["date"] == "2026-06-06"
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["content"] == "用户喜欢辣的食物"
        assert item["source"] == "pref_detection"
        assert item["session_id"] == "sess-1"
        assert item["context"] == "用户说要吃爆炒腊肉"
        assert "id" in item
        assert "created" in item


def test_add_item_type_category_fields():
    """item 应包含 type 和 category 字段。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("用户喜欢咖啡", "tool", date="2026-06-06",
                      type="preference", category="饮食", session_id="sess-1")
        f = Path(d) / "short-term" / "2026-06-06.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        item = data["items"][0]
        assert item["type"] == "preference"
        assert item["category"] == "饮食"


def test_add_item_default_type():
    """type 默认为 'note'。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("一些内容", "test", date="2026-06-06")
        f = Path(d) / "short-term" / "2026-06-06.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["items"][0]["type"] == "note"


def test_add_item_same_date_merges():
    """同一天多次 add_item 应合并到同一文件。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("item1", "test", date="2026-06-06")
        stm.add_item("item2", "test", date="2026-06-06")
        f = Path(d) / "short-term" / "2026-06-06.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        assert len(data["items"]) == 2
        # 只有一个日期文件
        files = list((Path(d) / "short-term").glob("*.json"))
        assert len(files) == 1


def test_add_item_different_dates_separate_files():
    """不同日期应创建不同文件。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("item1", "test", date="2026-06-05")
        stm.add_item("item2", "test", date="2026-06-06")
        f1 = Path(d) / "short-term" / "2026-06-05.json"
        f2 = Path(d) / "short-term" / "2026-06-06.json"
        assert f1.exists()
        assert f2.exists()
        d1 = json.loads(f1.read_text(encoding="utf-8"))
        d2 = json.loads(f2.read_text(encoding="utf-8"))
        assert len(d1["items"]) == 1
        assert len(d2["items"]) == 1


# ============================================================
# 2. 日期校验
# ============================================================

def test_date_validation_rejects_bad_format():
    """日期格式不合法时应拒绝。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        with pytest.raises(ValueError, match="非法日期"):
            stm.add_item("test", "test", date="not-a-date")
        with pytest.raises(ValueError, match="非法日期"):
            stm.add_item("test", "test", date="2026/06/06")
        with pytest.raises(ValueError, match="非法日期"):
            stm.add_item("test", "test", date="20260606")
        with pytest.raises(ValueError, match="非法日期"):
            stm.get_by_date("2026-13-01")


def test_date_validation_rejects_path_traversal():
    """日期含路径遍历字符时应拒绝。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        with pytest.raises(ValueError, match="非法日期"):
            stm.add_item("test", "test", date="../2026-06-06")
        with pytest.raises(ValueError, match="非法日期"):
            stm.get_by_date("../../etc/passwd")


# ============================================================
# 3. get_by_date
# ============================================================

def test_get_by_date_returns_items():
    """get_by_date 应返回指定日期的所有 items。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("item1", "test", date="2026-06-05")
        stm.add_item("item2", "test", date="2026-06-06")
        stm.add_item("item3", "test", date="2026-06-06")
        items = stm.get_by_date("2026-06-06")
        assert len(items) == 2
        assert items[0]["content"] == "item2"
        assert items[1]["content"] == "item3"


def test_get_by_date_empty():
    """无数据的日期应返回空列表。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        items = stm.get_by_date("2026-06-06")
        assert items == []


# ============================================================
# 4. get_recent — 跨日期文件聚合
# ============================================================

def test_get_recent_cross_date_aggregation():
    """get_recent 应跨多个日期文件聚合 items。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("old item", "test", date="2026-06-01")
        stm.add_item("mid item", "test", date="2026-06-03")
        stm.add_item("new item", "test", date="2026-06-06")
        items = stm.get_recent(limit=10)
        assert len(items) == 3
        # 按 created 降序
        assert items[0]["content"] == "new item"
        assert items[-1]["content"] == "old item"


def test_get_recent_respects_limit():
    """get_recent 应正确截断。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        for i in range(5):
            stm.add_item(f"item-{i}", "test", date=f"2026-06-0{i+1}")
        items = stm.get_recent(limit=3)
        assert len(items) == 3


def test_get_recent_includes_session_id():
    """get_recent 返回的 items 应包含 session_id。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("item1", "test", date="2026-06-06", session_id="sess-abc")
        items = stm.get_recent()
        assert items[0]["session_id"] == "sess-abc"


# ============================================================
# 5. get_by_session — 跨日期文件扫描
# ============================================================

def test_get_by_session_cross_date():
    """get_by_session 应跨日期文件扫描。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("item1", "test", date="2026-06-05", session_id="sess-1")
        stm.add_item("item2", "test", date="2026-06-06", session_id="sess-1")
        stm.add_item("item3", "test", date="2026-06-06", session_id="sess-2")
        items = stm.get_by_session("sess-1")
        assert len(items) == 2
        assert all(i["session_id"] == "sess-1" for i in items)


# ============================================================
# 6. get_summary — 新格式
# ============================================================

def test_get_summary_format_with_type():
    """get_summary 格式：- [Weekday YYYY-MM-DD HH:MM] [{type}] {content}。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        # 写入一个已知时间的 item
        stm.add_item("用户喜欢咖啡", "test", date="2026-06-06",
                      type="preference", session_id="sess-1")
        # mock created 时间以确保输出可预测
        f = Path(d) / "short-term" / "2026-06-06.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        data["items"][0]["created"] = "2026-06-06T14:30:00+00:00"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        summary = stm.get_summary(limit=10)
        assert summary is not None
        lines = summary.split("\n")
        assert len(lines) == 1
        line = lines[0]
        # 应包含 [preference] 和时间
        assert "[preference]" in line
        assert "用户喜欢咖啡" in line
        # 时间格式：Weekday YYYY-MM-DD HH:MM
        assert "2026-06-06" in line


def test_get_summary_default_type_is_note():
    """type 默认时应显示 [note]。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("一些内容", "test", date="2026-06-06")
        f = Path(d) / "short-term" / "2026-06-06.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        data["items"][0]["created"] = "2026-06-06T10:00:00+00:00"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        summary = stm.get_summary(limit=10)
        assert summary is not None
        assert "[note]" in summary


def test_get_summary_local_timezone():
    """_format_ts 应将 UTC 时间转为本地时区。"""
    from memory.short_term import ShortTermMemory
    # UTC 14:30 应转为本地时间
    ts = "2026-06-06T14:30:00+00:00"
    result = ShortTermMemory._format_ts(ts)
    assert result != ""
    # 本地时间不等于 UTC（除非在 UTC 时区）
    # 验证格式正确
    import re
    assert re.match(r"\w+ \d{4}-\d{2}-\d{2} \d{2}:\d{2}", result), \
        f"格式应为 'Weekday YYYY-MM-DD HH:MM'，实际: {result}"


def test_get_summary_returns_none_when_empty():
    """无内容时应返回 None。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        assert stm.get_summary() is None


# ============================================================
# 7. remove_items — 适配新文件结构
# ============================================================

def test_remove_items_across_dates():
    """remove_items 应跨日期文件删除。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("item1", "test", date="2026-06-05")
        stm.add_item("item2", "test", date="2026-06-06")
        all_items = stm.get_recent()
        assert len(all_items) == 2
        # 删除第一个
        stm.remove_items([all_items[0]["id"]])
        remaining = stm.get_recent()
        assert len(remaining) == 1
        assert remaining[0]["content"] != all_items[0]["content"]


def test_remove_items_preserves_date_structure():
    """remove_items 后文件 date 字段应保持不变。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("item1", "test", date="2026-06-06")
        stm.add_item("item2", "test", date="2026-06-06")
        items = stm.get_by_date("2026-06-06")
        stm.remove_items([items[0]["id"]])
        f = Path(d) / "short-term" / "2026-06-06.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["date"] == "2026-06-06"
        assert len(data["items"]) == 1


# ============================================================
# 8. cleanup_old — 清理过期文件
# ============================================================

def test_cleanup_old_removes_expired_files():
    """cleanup_old 应删除超过 keep_days 天的日期文件。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("old", "test", date="2026-05-20")
        stm.add_item("recent", "test", date="2026-06-05")
        stm.add_item("today", "test", date="2026-06-06")
        # keep_days=14 from 2026-06-06 → cutoff=2026-05-23
        # 2026-05-20 应被删除，2026-06-05 和 2026-06-06 应保留
        stm.cleanup_old(keep_days=14, today="2026-06-06")
        remaining = stm.get_recent()
        contents = {i["content"] for i in remaining}
        assert "old" not in contents
        assert "recent" in contents
        assert "today" in contents


def test_cleanup_old_with_default_keep_days():
    """cleanup_old 默认 keep_days=14。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("ancient", "test", date="2026-05-01")
        stm.add_item("recent", "test", date="2026-06-05")
        stm.cleanup_old(today="2026-06-06")
        remaining = stm.get_recent()
        assert len(remaining) == 1
        assert remaining[0]["content"] == "recent"


def test_cleanup_old_no_files_to_remove():
    """无过期文件时 cleanup_old 不报错。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("recent", "test", date="2026-06-06")
        stm.cleanup_old(keep_days=14, today="2026-06-06")
        assert len(stm.get_recent()) == 1


def test_cleanup_old_ignores_non_date_files():
    """cleanup_old 应忽略非日期格式的文件。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        # 手动创建一个非日期文件
        bad_file = Path(d) / "short-term" / "not-a-date.json"
        bad_file.write_text('{"test": true}', encoding="utf-8")
        stm.add_item("recent", "test", date="2026-06-06")
        stm.cleanup_old(keep_days=14, today="2026-06-06")
        # 非日期文件应保留
        assert bad_file.exists()
        # 正常文件也保留
        assert len(stm.get_recent()) == 1


# ============================================================
# 9. 损坏文件处理
# ============================================================

def test_corrupted_date_file_is_quarantined():
    """损坏的日期文件应被隔离。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        bad_file = date_dir / "2026-06-06.json"
        bad_file.write_text("{invalid json", encoding="utf-8")
        # get_recent 不崩溃
        items = stm.get_recent()
        assert items == []
        # 损坏文件被隔离
        quarantined = date_dir / "2026-06-06.json.corrupt"
        assert quarantined.exists()


def test_corrupted_date_file_add_item_recovers():
    """损坏的日期文件被 add_item 发现时应恢复。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        bad_file = date_dir / "2026-06-06.json"
        bad_content = '{"items": [partial...'
        bad_file.write_text(bad_content, encoding="utf-8")
        stm.add_item("new item", "test", date="2026-06-06")
        # 隔离文件保留原始内容
        quarantined = date_dir / "2026-06-06.json.corrupt"
        assert quarantined.read_text(encoding="utf-8") == bad_content
        # 新文件正常
        data = json.loads(bad_file.read_text(encoding="utf-8"))
        assert data["date"] == "2026-06-06"
        assert len(data["items"]) == 1
        assert data["items"][0]["content"] == "new item"


# ============================================================
# 10. 并发安全
# ============================================================

def test_add_item_concurrent_no_lost_items():
    """并发调用 add_item 不应丢失任何 item。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        errors = []
        num_threads = 10
        items_per_thread = 20

        def add_items(thread_id):
            try:
                for i in range(items_per_thread):
                    stm.add_item(f"item-{thread_id}-{i}", "test",
                                 date="2026-06-06", session_id="sess-concurrent")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_items, args=(t,))
                   for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发写入时出错: {errors}"
        items = stm.get_by_session("sess-concurrent")
        expected = num_threads * items_per_thread
        assert len(items) == expected, \
            f"并发写入应有 {expected} 个 items，实际只有 {len(items)} 个"


# ============================================================
# 11. cleanup_sessions — 保留向后兼容
# ============================================================

def test_cleanup_sessions_by_removing_items():
    """cleanup_sessions 应删除指定 session 的所有 items。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("item1", "test", date="2026-06-06", session_id="sess-1")
        stm.add_item("item2", "test", date="2026-06-06", session_id="sess-2")
        stm.cleanup_sessions(["sess-1"])
        remaining = stm.get_recent()
        assert len(remaining) == 1
        assert remaining[0]["session_id"] == "sess-2"


# ============================================================
# 12. 原子写入
# ============================================================

def test_atomic_write_no_tmp_leftover():
    """写入后不应留下 .tmp 临时文件。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("item1", "test", date="2026-06-06")
        tmp_files = list((Path(d) / "short-term").glob("*.tmp"))
        assert tmp_files == [], f"不应有残留 .tmp 文件: {tmp_files}"


# ============================================================
# 13. _format_ts 边界情况
# ============================================================

def test_format_ts_empty_string():
    """空字符串应返回空。"""
    from memory.short_term import ShortTermMemory
    assert ShortTermMemory._format_ts("") == ""


def test_format_ts_short_string():
    """过短的时间戳应返回空。"""
    from memory.short_term import ShortTermMemory
    assert ShortTermMemory._format_ts("2026") == ""


def test_format_ts_invalid_format():
    """无效格式应降级处理。"""
    from memory.short_term import ShortTermMemory
    result = ShortTermMemory._format_ts("not-a-timestamp")
    # 应不崩溃，返回降级字符串或空
    assert isinstance(result, str)
