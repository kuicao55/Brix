"""DreamManager 测试。"""
import asyncio
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


def test_should_dream_returns_false_initially():
    """初始状态不应触发 dream。"""
    from memory.dream import DreamManager

    with tempfile.TemporaryDirectory() as d:
        dm = DreamManager(Path(d))
        assert dm.should_dream() is False


def test_should_dream_after_thresholds():
    """满足双门槛后应触发 dream。"""
    from memory.dream import DreamManager

    with tempfile.TemporaryDirectory() as d:
        dm = DreamManager(Path(d))
        # 模拟 5 个新会话
        for _ in range(5):
            dm.on_session_created()
        # 模拟 24h 前的状态
        state_path = Path(d) / "dream" / "dream-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "last_dream_at": (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
            "sessions_since_dream": 5,
            "total_dreams": 0,
        }
        state_path.write_text(json.dumps(state))
        dm = DreamManager(Path(d))  # 重新加载
        assert dm.should_dream() is True


def test_on_session_created_increments_counter():
    """on_session_created 应递增会话计数。"""
    from memory.dream import DreamManager

    with tempfile.TemporaryDirectory() as d:
        dm = DreamManager(Path(d))
        dm.on_session_created()
        dm.on_session_created()
        state = json.loads((Path(d) / "dream" / "dream-state.json").read_text())
        assert state["sessions_since_dream"] == 2


def test_run_updates_state():
    """run 完成后应更新 dream-state。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        # 添加一些短期记忆
        stm.add_item("sess-1", "用户喜欢辣的食物", "pref_detection")

        # mock LLM 返回合法分类 JSON
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "core": ["用户喜欢辣的食物"],
            "topics": {},
            "discard": [],
        }))

        # 需要手动设置状态使 should_dream 返回 True
        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        state = dm._state
        assert state["sessions_since_dream"] == 0
        assert state["total_dreams"] == 1


def test_malformed_llm_response_does_not_cleanup_sessions():
    """当 LLM 返回无法解析的内容时，不应清理短期记忆。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        # 添加短期记忆
        stm.add_item("sess-1", "用户喜欢咖啡", "pref_detection")
        stm.add_item("sess-2", "用户喜欢茶", "pref_detection")

        # mock get_recent 返回带 session_id 的 items（使 cleanup_sessions 能提取到 session）
        original_get_recent = stm.get_recent
        def get_recent_with_session_id(limit=50):
            items = original_get_recent(limit)
            for item in items:
                # 给每个 item 注入 session_id，使 cleanup_sessions 能提取到
                item["session_id"] = "sess-1" if "咖啡" in item.get("content", "") else "sess-2"
            return items
        stm.get_recent = get_recent_with_session_id

        # mock LLM 返回无法解析的文本
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content="这不是JSON")

        # 设置状态使 should_dream 返回 True
        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 会话不应被清理 —— 内容应仍然存在
        assert len(stm.get_by_session("sess-1")) > 0, "sess-1 内容不应在 LLM 解析失败时被清理"
        assert len(stm.get_by_session("sess-2")) > 0, "sess-2 内容不应在 LLM 解析失败时被清理"


def test_invalid_classification_schema_handled():
    """当 LLM 返回类型不正确的分类结果时，应过滤无效条目。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        stm.add_item("sess-1", "用户喜欢咖啡", "pref_detection")

        # mock LLM 返回类型错误的 JSON：core 含非字符串，topics 含非字符串列表
        mock_llm = AsyncMock()
        bad_classification = json.dumps({
            "core": [123, "valid item", None],  # 混合类型，应只保留 "valid item"
            "topics": {"topic1": [456, "valid content"]},  # list 内有 int，应只保留 "valid content"
            "discard": [],
        })
        mock_llm.chat.return_value = MagicMock(content=bad_classification)

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        # 不应抛异常
        asyncio.run(dm.run(mock_llm, "test/model"))

        # 状态应正常更新
        assert dm._state["total_dreams"] == 1

        # 验证只有有效字符串被写入 user.md（非字符串条目应被过滤）
        user_content = um.load()
        assert "valid item" in user_content, "有效字符串应被写入"
        assert "123" not in user_content, "非字符串 core 条目应被过滤"
        assert "None" not in user_content, "None core 条目应被过滤"


def test_future_timestamp_does_not_suppress_dream():
    """当 last_dream_at 在未来时（时钟偏移），应触发 dream 而非永久压制。"""
    from memory.dream import DreamManager

    with tempfile.TemporaryDirectory() as d:
        dm = DreamManager(Path(d))
        # 设置 last_dream_at 为未来时间
        dm._state["last_dream_at"] = (datetime.now(timezone.utc) + timedelta(hours=10)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()
        dm = DreamManager(Path(d))  # 重新加载
        # 未来时间应视为无效，满足 session 门槛后触发
        assert dm.should_dream() is True


def test_non_ascii_topic_names_sanitized():
    """非 ASCII 主题名（如 C++编程、用户偏好（重要））应被安全处理，不崩溃。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        stm.add_item("sess-1", "用户喜欢 C++ 编程", "pref_detection")

        # mock LLM 返回含非 ASCII 主题名的分类结果
        mock_llm = AsyncMock()
        classification = json.dumps({
            "core": [],
            "topics": {
                "C++编程": ["用户喜欢 C++ 编程"],
                "用户偏好（重要）": ["用户偏好红茶"],
            },
            "discard": [],
        })
        mock_llm.chat.return_value = MagicMock(content=classification)

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        # 不应抛异常
        asyncio.run(dm.run(mock_llm, "test/model"))

        # 验证主题被写入长期记忆（文件名应为 ASCII-safe slug）
        assert dm._state["total_dreams"] == 1, "成功完成应递增 total_dreams"
        # 长期记忆目录中应有对应的 .md 文件
        topic_files = list((Path(d) / "long-term").glob("*.md"))
        assert len(topic_files) >= 1, "应至少写入一个主题文件"


def test_classification_failure_preserves_state():
    """分类失败时，不应重置会话计数或递增 total_dreams。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        stm.add_item("sess-1", "用户喜欢咖啡", "pref_detection")

        # mock LLM 抛出异常（模拟网络错误等）
        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = RuntimeError("LLM 连接超时")

        # 设置初始状态
        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._state["total_dreams"] = 2
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 关键断言：分类失败不应修改状态
        assert dm._state["sessions_since_dream"] == 5, \
            "分类失败时 sessions_since_dream 应保持不变"
        assert dm._state["total_dreams"] == 2, \
            "分类失败时 total_dreams 不应递增"


def test_write_failure_skips_cleanup_and_state_advance():
    """Issue 1: 长期记忆写入失败时，不应清理短期记忆，也不应推进 dream 状态。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        stm.add_item("sess-1", "用户喜欢咖啡", "pref_detection")

        # mock LLM 返回分类结果，含 topics
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "core": [],
            "topics": {"coffee": ["用户喜欢咖啡"]},
            "discard": [],
        }))

        # mock long_term.write_topic 抛异常，模拟磁盘满
        ltm.write_topic = MagicMock(side_effect=OSError("磁盘已满"))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._state["total_dreams"] = 2
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 写入失败时，不应清理短期记忆
        assert len(stm.get_by_session("sess-1")) > 0, \
            "写入失败时短期记忆不应被清理"
        # 写入失败时，不应推进 dream 状态
        assert dm._state["sessions_since_dream"] == 5, \
            "写入失败时 sessions_since_dream 应保持不变"
        assert dm._state["total_dreams"] == 2, \
            "写入失败时 total_dreams 不应递增"


def test_get_recent_includes_session_id():
    """Issue 2: get_recent 返回的 items 应包含 session_id 字段。"""
    from memory.short_term import ShortTermMemory

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        stm.add_item("sess-abc", "测试内容", "pref_detection")

        items = stm.get_recent(limit=10)
        assert len(items) == 1
        assert items[0].get("session_id") == "sess-abc", \
            f"item 应包含 session_id，实际 keys: {list(items[0].keys())}"


def test_slug_collision_merges_contents():
    """Issue 3: 多个非 ASCII 主题映射到同一 slug 时，内容应合并而非覆盖。"""
    from memory.dream import DreamManager

    # 两个完全不同的非 ASCII 主题名，slugify 后都变成 "untitled"
    classification = {
        "core": [],
        "topics": {
            "日本語": ["记忆A"],
            "中文主题": ["记忆B"],
        },
        "discard": [],
    }
    validated = DreamManager._validate_classification(classification)

    # 两者 slugify 后都是 "untitled"（全非 ASCII），内容应合并
    assert "untitled" in validated["topics"], \
        f"两个非 ASCII 主题应映射到 'untitled'，实际 keys: {list(validated['topics'].keys())}"
    contents = validated["topics"]["untitled"]
    assert "记忆A" in contents, f"'记忆A' 应在合并结果中，实际: {contents}"
    assert "记忆B" in contents, f"'记忆B' 应在合并结果中，实际: {contents}"


# --- Issue 1: session 级清理删除未处理的记忆 ---

def test_dream_cleanup_only_removes_processed_items():
    """Issue 1: Dream run 应只清理被处理的 items，不应删除整个 session 文件。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        # 在同一个 session 中添加多个 items
        # get_recent(limit=200) 会返回这些
        for i in range(5):
            stm.add_item("sess-many", f"item-{i}", "pref_detection")

        # mock LLM 分类
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "core": [],
            "topics": {"general": ["item-0", "item-1"]},
            "discard": ["item-2", "item-3", "item-4"],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 关键断言：所有被采样到的 items 应被清理（通过 remove_items 而非 cleanup_sessions）
        remaining = stm.get_by_session("sess-many")
        assert len(remaining) == 0, \
            f"所有被采样的 items 应被清理，实际剩余 {len(remaining)} 个"
        # session 文件本身不应被删除（cleanup_sessions 已移除）
        session_file = Path(d) / "short-term" / "sess-many.json"
        assert session_file.exists(), "session 文件不应被整个删除，应通过 item 级删除"


def test_dream_cleanup_preserves_unprocessed_items_in_session():
    """Issue 1: 当 session 有部分 items 未被采样到时，Dream 不应销毁它们。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        # 在同一个 session 中添加多个 items
        for i in range(10):
            stm.add_item("sess-big", f"item-{i}", "pref_detection")

        # 保存所有 item IDs
        all_items = stm.get_by_session("sess-big")
        all_ids = {item["id"] for item in all_items}

        # mock get_recent 只返回前 5 个（模拟 limit 截断）
        original_get_recent = stm.get_recent
        sampled_ids = set()

        def mock_get_recent(limit=50):
            items = original_get_recent(limit=5)
            for item in items:
                item["session_id"] = "sess-big"
            return items

        stm.get_recent = mock_get_recent

        # mock LLM
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "core": [],
            "topics": {},
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 验证：session 中未被采样的 items 不应被销毁
        remaining = stm.get_by_session("sess-big")
        # 应该至少有 5 个 items 未被采样到，不应被删除
        assert len(remaining) >= 5, \
            f"未被采样的 items 不应被销毁，应至少剩 5 个，实际剩 {len(remaining)} 个"


# --- Issue 2: 降级模式下 sink 不可用仍清理 ---

def test_degraded_long_term_none_prevents_cleanup():
    """Issue 2: 当 _long_term 为 None 但有 topics 时，不应清理短期记忆。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        # _long_term = None
        dm = DreamManager(Path(d), stm, long_term=None, user_manager=um)

        stm.add_item("sess-1", "有价值的知识", "pref_detection")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "core": [],
            "topics": {"knowledge": ["有价值的知识"]},
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # _long_term 为 None 但 topics 非空 => 应视为写入失败
        assert len(stm.get_by_session("sess-1")) > 0, \
            "long_term 不可用时有 topics 应视为写入失败，不应清理短期记忆"
        assert dm._state["sessions_since_dream"] == 5, \
            "写入失败时不应推进 dream 状态"
        assert dm._state["total_dreams"] == 0, \
            "写入失败时不应递增 total_dreams"


def test_degraded_user_manager_none_prevents_cleanup():
    """Issue 2: 当 _user_manager 为 None 但有 core items 时，不应清理短期记忆。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        # _user_manager = None
        dm = DreamManager(Path(d), stm, long_term=ltm, user_manager=None)

        stm.add_item("sess-1", "核心记忆", "pref_detection")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "core": ["核心记忆"],
            "topics": {},
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # _user_manager 为 None 但 core 非空 => 应视为写入失败
        assert len(stm.get_by_session("sess-1")) > 0, \
            "user_manager 不可用时有 core items 应视为写入失败，不应清理短期记忆"
        assert dm._state["sessions_since_dream"] == 5, \
            "写入失败时不应推进 dream 状态"


def test_degraded_both_sinks_none_prevents_cleanup():
    """Issue 2: 当 long_term 和 user_manager 都为 None 时，不应清理。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        # 两个 sink 都为 None
        dm = DreamManager(Path(d), stm, long_term=None, user_manager=None)

        stm.add_item("sess-1", "一些内容", "pref_detection")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "core": ["核心"],
            "topics": {"topic1": ["知识"]},
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        assert len(stm.get_by_session("sess-1")) > 0, \
            "所有 sink 不可用时不应清理短期记忆"


def test_all_discard_with_no_sinks_still_cleans():
    """Issue 2: 当所有 items 都是 discard 且没有 core/topics 时，即使 sink 为 None 也可以安全清理。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        dm = DreamManager(Path(d), stm, long_term=None, user_manager=None)

        stm.add_item("sess-1", "垃圾信息", "pref_detection")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "core": [],
            "topics": {},
            "discard": ["垃圾信息"],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 全部 discard，不需要写入任何 sink，可以安全清理
        assert dm._state["total_dreams"] == 1, \
            "全部 discard 时应正常完成 dream"
