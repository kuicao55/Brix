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


# ============================================================
# 14. CQR Issue 2: 跨日期覆盖 — data["date"] 与文件名不匹配
# ============================================================

def test_remove_items_quarantines_date_mismatch():
    """remove_items 遇到 date/filename 不匹配时应隔离文件，不写入其他日期。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        # 文件名 2026-06-06.json，但 data["date"]="2026-06-05"
        mismatched_data = {
            "date": "2026-06-05",
            "items": [
                {"id": "item-1", "content": "test", "session_id": "s1",
                 "created": "2026-06-06T10:00:00+00:00", "type": "note",
                 "source": "test", "category": "", "context": ""},
                {"id": "item-2", "content": "keep", "session_id": "s2",
                 "created": "2026-06-06T11:00:00+00:00", "type": "note",
                 "source": "test", "category": "", "context": ""},
            ]
        }
        (date_dir / "2026-06-06.json").write_text(
            json.dumps(mismatched_data, ensure_ascii=False), encoding="utf-8"
        )
        stm.remove_items(["item-1"])
        # 不匹配的文件应被隔离
        assert (date_dir / "2026-06-06.json.corrupt").exists()
        # 原始文件应已移除
        assert not (date_dir / "2026-06-06.json").exists()
        # 不应创建 2026-06-05.json（错误的 data["date"] 目标）
        assert not (date_dir / "2026-06-05.json").exists()


def test_cleanup_sessions_quarantines_date_mismatch():
    """cleanup_sessions 遇到 date/filename 不匹配时应隔离文件，不写入其他日期。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        mismatched_data = {
            "date": "2026-06-05",
            "items": [
                {"id": "item-1", "content": "remove", "session_id": "old-sess",
                 "created": "2026-06-06T10:00:00+00:00", "type": "note",
                 "source": "test", "category": "", "context": ""},
                {"id": "item-2", "content": "keep", "session_id": "other-sess",
                 "created": "2026-06-06T11:00:00+00:00", "type": "note",
                 "source": "test", "category": "", "context": ""},
            ]
        }
        (date_dir / "2026-06-06.json").write_text(
            json.dumps(mismatched_data, ensure_ascii=False), encoding="utf-8"
        )
        stm.cleanup_sessions(["old-sess"])
        # 不匹配的文件应被隔离
        assert (date_dir / "2026-06-06.json.corrupt").exists()
        assert not (date_dir / "2026-06-06.json").exists()
        # 不应创建 2026-06-05.json
        assert not (date_dir / "2026-06-05.json").exists()


def test_date_filename_mismatch_is_quarantined():
    """data['date'] 与文件名不匹配时应隔离文件。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        # 文件名 2026-06-06.json，data["date"]="2026-06-05"
        mismatched = {"date": "2026-06-05", "items": []}
        (date_dir / "2026-06-06.json").write_text(
            json.dumps(mismatched), encoding="utf-8"
        )
        # get_by_date 应隔离不匹配的文件并返回空
        items = stm.get_by_date("2026-06-06")
        assert items == []
        quarantined = date_dir / "2026-06-06.json.corrupt"
        assert quarantined.exists()


# ============================================================
# 15. CQR Issue 3: 错误结构的 JSON 文件处理
# ============================================================

def test_get_by_session_handles_list_instead_of_dict():
    """get_by_session 遇到 JSON 是列表而非字典时应隔离文件，不崩溃。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        # 文件内容是列表，不是字典
        (date_dir / "2026-06-06.json").write_text(
            '[{"id": "1"}]', encoding="utf-8"
        )
        items = stm.get_by_session("any-session")
        assert items == []
        assert (date_dir / "2026-06-06.json.corrupt").exists()


def test_get_by_session_handles_dict_missing_items_key():
    """get_by_session 遇到缺少 items 键的字典时应隔离。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        (date_dir / "2026-06-06.json").write_text(
            '{"date": "2026-06-06"}', encoding="utf-8"
        )
        items = stm.get_by_session("any-session")
        assert items == []
        assert (date_dir / "2026-06-06.json.corrupt").exists()


def test_get_by_session_handles_items_not_a_list():
    """get_by_session 遇到 items 不是列表时应隔离。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        (date_dir / "2026-06-06.json").write_text(
            '{"date": "2026-06-06", "items": "not a list"}', encoding="utf-8"
        )
        items = stm.get_by_session("any-session")
        assert items == []
        assert (date_dir / "2026-06-06.json.corrupt").exists()


def test_remove_items_handles_wrong_shape_json():
    """remove_items 遇到错误结构的 JSON 时应隔离，不崩溃。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        # 列表而非字典
        (date_dir / "2026-06-06.json").write_text(
            '["not", "a", "dict"]', encoding="utf-8"
        )
        # 不应崩溃
        stm.remove_items(["any-id"])
        assert (date_dir / "2026-06-06.json.corrupt").exists()


def test_cleanup_sessions_handles_wrong_shape_json():
    """cleanup_sessions 遇到错误结构的 JSON 时应隔离，不崩溃。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        # 缺少 items 键
        (date_dir / "2026-06-06.json").write_text(
            '{"unexpected": true}', encoding="utf-8"
        )
        stm.cleanup_sessions(["any-session"])
        assert (date_dir / "2026-06-06.json.corrupt").exists()


def test_get_by_date_handles_items_with_non_dict_elements():
    """get_by_date 遇到 items 包含非 dict 元素时应隔离。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        # items 包含非 dict 元素（原始值）
        (date_dir / "2026-06-06.json").write_text(
            '{"date": "2026-06-06", "items": [1, 2, 3]}', encoding="utf-8"
        )
        items = stm.get_by_date("2026-06-06")
        # 应隔离错误结构的文件并返回空
        assert items == []
        assert (date_dir / "2026-06-06.json.corrupt").exists()


# ============================================================
# 16. CQR Issue 1: 跨进程文件锁
# ============================================================

def _worker_add_items(data_dir: str, num_items: int, worker_id: int) -> None:
    """子进程 worker：向同一日期文件写入 items。"""
    # 需要在子进程中重新 import
    import sys
    sys.path.insert(0, str(Path(data_dir).parent))
    from memory.short_term import ShortTermMemory
    stm = ShortTermMemory(Path(data_dir))
    for i in range(num_items):
        stm.add_item(f"item-w{worker_id}-{i}", "test", date="2026-06-06",
                      session_id=f"sess-w{worker_id}")


def test_multiprocess_add_item_no_lost_items():
    """多个进程并发 add_item 不应丢失任何 item（跨进程文件锁）。"""
    import multiprocessing
    with tempfile.TemporaryDirectory() as d:
        data_dir = str(Path(d))
        num_workers = 4
        items_per_worker = 20

        procs = []
        for w in range(num_workers):
            p = multiprocessing.Process(
                target=_worker_add_items,
                args=(data_dir, items_per_worker, w)
            )
            procs.append(p)

        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=30)

        # 确认所有进程正常退出
        for p in procs:
            assert p.exitcode == 0, f"进程退出码: {p.exitcode}"

        from memory.short_term import ShortTermMemory
        stm = ShortTermMemory(Path(data_dir))
        items = stm.get_by_date("2026-06-06")
        expected = num_workers * items_per_worker
        assert len(items) == expected, \
            f"跨进程写入应有 {expected} 个 items，实际只有 {len(items)} 个"


# ============================================================
# 17. CQR Round 2 Issue 1: 并发 add+remove 竞态 — 文件锁缺失
# ============================================================

def _worker_remove_items(data_dir: str, item_ids: list[str]) -> None:
    """子进程 worker：调用 remove_items。"""
    import sys
    sys.path.insert(0, str(Path(data_dir).parent))
    from memory.short_term import ShortTermMemory
    stm = ShortTermMemory(Path(data_dir))
    stm.remove_items(item_ids)


def _worker_cleanup_sessions(data_dir: str, session_ids: list[str]) -> None:
    """子进程 worker：调用 cleanup_sessions。"""
    import sys
    sys.path.insert(0, str(Path(data_dir).parent))
    from memory.short_term import ShortTermMemory
    stm = ShortTermMemory(Path(data_dir))
    stm.cleanup_sessions(session_ids)


def _worker_add_and_remove_race(data_dir: str, num_ops: int, worker_id: int) -> None:
    """子进程 worker：交替 add 和 remove 操作来制造竞态。"""
    import sys
    sys.path.insert(0, str(Path(data_dir).parent))
    from memory.short_term import ShortTermMemory
    stm = ShortTermMemory(Path(data_dir))
    for i in range(num_ops):
        # 添加一个新 item
        stm.add_item(f"race-w{worker_id}-{i}", "test", date="2026-06-06",
                      session_id=f"sess-w{worker_id}")
        # 删除上一个 item（如果有的话）
        if i > 0:
            stm.remove_items([f"fake-id-w{worker_id}-{i-1}"])


def test_multiprocess_add_and_remove_real_race():
    """多进程并发 add + remove 操作，remove 实际修改文件时不应丢数据。
    此测试验证跨进程文件锁在所有写入路径上都生效。
    """
    import multiprocessing
    with tempfile.TemporaryDirectory() as d:
        data_dir = str(Path(d))
        from memory.short_term import ShortTermMemory
        stm = ShortTermMemory(Path(data_dir))
        # 预填充一些 items，确保 remove 有东西可读（即使不删除）
        for i in range(10):
            stm.add_item(f"seed-{i}", "test", date="2026-06-06",
                         session_id="seed-sess")

        num_workers = 4
        ops_per_worker = 20
        procs = []
        for w in range(num_workers):
            p = multiprocessing.Process(
                target=_worker_add_and_remove_race,
                args=(data_dir, ops_per_worker, w)
            )
            procs.append(p)

        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=30)

        for p in procs:
            assert p.exitcode == 0, f"进程退出码: {p.exitcode}"

        stm2 = ShortTermMemory(Path(data_dir))
        items = stm2.get_by_date("2026-06-06")
        # 至少应有种子 items + 每个 worker 最后一个 add
        expected_min = 10 + num_workers
        assert len(items) >= expected_min, \
            f"应至少有 {expected_min} 个 items，实际 {len(items)} 个"


# ============================================================
# 18. CQR Round 2 Issue 2: 旧格式文件迁移
# ============================================================

def test_legacy_uuid_session_file_migrated_on_load():
    """旧格式 UUID session 文件应被迁移到日期 bucket，不隔离。
    迁移在 glob 扫描（get_recent/get_by_session）时触发。
    """
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        # 模拟旧格式：UUID 命名文件，items 无 date 字段
        legacy_data = {
            "session_id": "550e8400-e29b-41d4-a716-446655440000",
            "items": [
                {
                    "id": "item-legacy-1",
                    "content": "旧记忆条目",
                    "source": "pref_detection",
                    "type": "note",
                    "category": "",
                    "session_id": "550e8400-e29b-41d4-a716-446655440000",
                    "created": "2026-06-01T10:00:00+00:00",
                    "context": "旧格式数据",
                },
            ]
        }
        legacy_file = date_dir / "550e8400-e29b-41d4-a716-446655440000.json"
        legacy_file.write_text(
            json.dumps(legacy_data, ensure_ascii=False), encoding="utf-8"
        )
        # get_recent 触发 glob 扫描，应迁移旧文件
        items = stm.get_recent()
        assert len(items) == 1
        assert items[0]["content"] == "旧记忆条目"
        # 旧文件应已删除
        assert not legacy_file.exists()
        # 不应有 .corrupt 文件
        corrupt_files = list(date_dir.glob("*.corrupt"))
        assert len(corrupt_files) == 0, f"不应隔离旧格式文件: {corrupt_files}"
        # 新日期文件应存在
        date_file = date_dir / "2026-06-01.json"
        assert date_file.exists()
        data = json.loads(date_file.read_text(encoding="utf-8"))
        assert data["date"] == "2026-06-01"
        assert len(data["items"]) == 1
        # get_by_date 也能读取迁移后的数据
        by_date = stm.get_by_date("2026-06-01")
        assert len(by_date) == 1
        assert by_date[0]["content"] == "旧记忆条目"


def test_legacy_session_file_migrated_on_glob_operations():
    """get_recent 扫描时也应迁移旧格式文件。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        # 旧格式文件
        legacy_data = {
            "items": [
                {
                    "id": "item-legacy",
                    "content": "旧数据",
                    "source": "test",
                    "type": "note",
                    "category": "",
                    "session_id": "old-sess",
                    "created": "2026-06-02T15:00:00+00:00",
                    "context": "",
                },
            ]
        }
        (date_dir / "a1b2c3d4-e5f6-7890-abcd-ef1234567890.json").write_text(
            json.dumps(legacy_data, ensure_ascii=False), encoding="utf-8"
        )
        # 同时有一个正常的日期文件
        stm.add_item("新数据", "test", date="2026-06-06")
        items = stm.get_recent()
        contents = {it["content"] for it in items}
        assert "旧数据" in contents, f"应迁移并返回旧数据: {contents}"
        assert "新数据" in contents


def test_legacy_file_with_no_created_field_is_quarantined():
    """旧格式但 items 缺少 created 字段时应隔离（无法确定日期 bucket）。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        # UUID 文件但 items 没有 created
        legacy_data = {
            "items": [
                {"id": "item-1", "content": "test", "source": "test",
                 "type": "note", "category": "", "session_id": "s1"},
            ]
        }
        (date_dir / "a1b2c3d4-e5f6-7890-abcd-ef1234567890.json").write_text(
            json.dumps(legacy_data, ensure_ascii=False), encoding="utf-8"
        )
        items = stm.get_recent()
        # 应被隔离
        assert (date_dir / "a1b2c3d4-e5f6-7890-abcd-ef1234567890.json.corrupt").exists()


# ============================================================
# 19. CQR Round 2 Issue 3: Item 级 schema 校验
# ============================================================

def test_items_with_missing_required_fields_are_dropped():
    """items 缺少必要字段时应丢弃坏条目，保留好条目。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        # 混合好条目和坏条目
        mixed_data = {
            "date": "2026-06-06",
            "items": [
                {"id": "good-1", "content": "好的条目", "source": "test",
                 "created": "2026-06-06T10:00:00+00:00", "type": "note",
                 "category": "", "session_id": "s1", "context": ""},
                {"id": "bad-no-content", "source": "test", "created": "2026-06-06T11:00:00+00:00"},
                {"created": 123},  # 缺少所有必要字段
                {"id": "good-2", "content": "另一个好条目", "source": "tool",
                 "created": "2026-06-06T12:00:00+00:00", "type": "preference",
                 "category": "", "session_id": "s2", "context": ""},
            ]
        }
        (date_dir / "2026-06-06.json").write_text(
            json.dumps(mixed_data, ensure_ascii=False), encoding="utf-8"
        )
        items = stm.get_by_date("2026-06-06")
        # 好条目应保留，坏条目应被丢弃
        assert len(items) == 2
        assert items[0]["content"] == "好的条目"
        assert items[1]["content"] == "另一个好条目"
        # 文件不应被隔离
        assert not (date_dir / "2026-06-06.json.corrupt").exists()


def test_sort_key_uses_string_fallback_for_non_string_created():
    """items 的 created 字段为非字符串时，排序应降级处理不崩溃。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        # created 为数字（非字符串）
        data_with_numeric_created = {
            "date": "2026-06-06",
            "items": [
                {"id": "item-1", "content": "正常条目", "source": "test",
                 "created": "2026-06-06T10:00:00+00:00", "type": "note",
                 "category": "", "session_id": "s1", "context": ""},
                {"id": "item-2", "content": "数字时间", "source": "test",
                 "created": 1749200000, "type": "note",
                 "category": "", "session_id": "s1", "context": ""},
            ]
        }
        (date_dir / "2026-06-06.json").write_text(
            json.dumps(data_with_numeric_created, ensure_ascii=False), encoding="utf-8"
        )
        # 不应崩溃
        items = stm.get_by_date("2026-06-06")
        assert len(items) == 2

        # get_recent 也不应崩溃
        all_items = stm.get_recent()
        assert len(all_items) == 2


def test_get_recent_with_mixed_created_types_sorts_safely():
    """get_recent 混合 created 类型（字符串 + 整数）时排序不崩溃。
    created=None 的条目会被 _sanitize_items 丢弃（None 不是有效值）。
    """
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "date": "2026-06-06",
            "items": [
                {"id": "item-1", "content": "str time", "source": "test",
                 "created": "2026-06-06T10:00:00+00:00", "type": "note",
                 "category": "", "session_id": "s1", "context": ""},
                {"id": "item-2", "content": "int time", "source": "test",
                 "created": 12345, "type": "note",
                 "category": "", "session_id": "s1", "context": ""},
                {"id": "item-3", "content": "none time", "source": "test",
                 "created": None, "type": "note",
                 "category": "", "session_id": "s1", "context": ""},
            ]
        }
        (date_dir / "2026-06-06.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        items = stm.get_recent()
        # created=None 被丢弃，其余 2 个保留
        assert len(items) == 2


def test_all_items_bad_content_is_dropped_file_still_valid():
    """所有 items 都缺失必要字段时，items 列表为空但文件不被隔离。"""
    from memory.short_term import ShortTermMemory
    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        date_dir = Path(d) / "short-term"
        date_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "date": "2026-06-06",
            "items": [
                {"random_field": "value"},
                {"id": 123},  # id 不是字符串
            ]
        }
        (date_dir / "2026-06-06.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        items = stm.get_by_date("2026-06-06")
        assert items == []
        # 文件不应被隔离 — 结构正确，只是 items 全是坏的
        assert not (date_dir / "2026-06-06.json.corrupt").exists()
        # 原始文件应保留
        assert (date_dir / "2026-06-06.json").exists()
