"""DreamManager 测试。"""
import asyncio
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


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
        stm.add_item("用户喜欢辣的食物", "pref_detection", session_id="sess-1")

        # mock LLM 返回合法分类 JSON（6-key 格式）
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": ["用户喜欢辣的食物"],
            "knowledge": [],
            "work": [],
            "history": [],
            "soul": [],
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
        stm.add_item("用户喜欢咖啡", "pref_detection", session_id="sess-1")
        stm.add_item("用户喜欢茶", "pref_detection", session_id="sess-2")

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

        stm.add_item("用户喜欢咖啡", "pref_detection", session_id="sess-1")

        # mock LLM 返回类型错误的 JSON：user 含非字符串
        mock_llm = AsyncMock()
        bad_classification = json.dumps({
            "user": [123, "valid item", None],  # 混合类型，应只保留 "valid item"
            "knowledge": [456, "valid content"],  # list 内有 int，应只保留 "valid content"
            "work": [],
            "history": [],
            "soul": [],
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
        assert "123" not in user_content, "非字符串 user 条目应被过滤"
        assert "None" not in user_content, "None user 条目应被过滤"


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
    """非 ASCII 内容应被安全处理，不崩溃。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        stm.add_item("用户喜欢 C++ 编程", "pref_detection", session_id="sess-1")

        # mock LLM 返回含非 ASCII 内容的分类结果（6-key 格式）
        mock_llm = AsyncMock()
        classification = json.dumps({
            "user": [],
            "knowledge": ["用户喜欢 C++ 编程"],
            "work": [],
            "history": [],
            "soul": [],
            "discard": ["用户偏好红茶"],
        })
        mock_llm.chat.return_value = MagicMock(content=classification)

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        # 不应抛异常
        asyncio.run(dm.run(mock_llm, "test/model"))

        # 验证内容被写入长期记忆
        assert dm._state["total_dreams"] == 1, "成功完成应递增 total_dreams"
        content = ltm.read_topic("knowledge.md")
        assert "用户喜欢 C++ 编程" in content, "knowledge 内容应写入 knowledge.md"


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

        stm.add_item("用户喜欢咖啡", "pref_detection", session_id="sess-1")

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

        stm.add_item("用户喜欢咖啡", "pref_detection", session_id="sess-1")

        # mock LLM 返回分类结果，含 knowledge
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": [],
            "knowledge": ["用户喜欢咖啡"],
            "work": [],
            "history": [],
            "soul": [],
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
        stm.add_item("测试内容", "pref_detection", session_id="sess-abc")

        items = stm.get_recent(limit=10)
        assert len(items) == 1
        assert items[0].get("session_id") == "sess-abc", \
            f"item 应包含 session_id，实际 keys: {list(items[0].keys())}"


def test_validate_classification_list_keys():
    """五路径: _validate_classification 对 list 类型 key 的验证。"""
    from memory.dream import DreamManager

    # 6-key 格式，所有值都是 list[str]
    classification = {
        "user": ["用户信息"],
        "knowledge": ["知识A", "知识B"],
        "work": ["工作内容"],
        "history": ["历史事件"],
        "soul": ["性格特征"],
        "discard": ["垃圾"],
    }
    validated = DreamManager._validate_classification(classification)

    assert validated["user"] == ["用户信息"]
    assert validated["knowledge"] == ["知识A", "知识B"]
    assert validated["work"] == ["工作内容"]
    assert validated["history"] == ["历史事件"]
    assert validated["soul"] == ["性格特征"]
    assert validated["discard"] == ["垃圾"]


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
            stm.add_item(f"item-{i}", "pref_detection", session_id="sess-many")

        # mock LLM 分类（6-key 格式）
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": [],
            "knowledge": ["item-0", "item-1"],
            "work": [],
            "history": [],
            "soul": [],
            "discard": ["item-2", "item-3", "item-4"],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 关键断言：所有被采样到的 items 应被清理（通过 remove_items 而非删除整个文件）
        remaining = stm.get_by_session("sess-many")
        assert len(remaining) == 0, \
            f"所有被采样的 items 应被清理，实际剩余 {len(remaining)} 个"
        # 日期文件本身不应被删除（应通过 item 级删除）
        date_files = list((Path(d) / "short-term").glob("*.json"))
        assert len(date_files) >= 1, "日期文件不应被整个删除，应通过 item 级删除"


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
            stm.add_item(f"item-{i}", "pref_detection", session_id="sess-big")

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

        # mock LLM（6-key 格式）
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": [],
            "knowledge": [],
            "work": [],
            "history": [],
            "soul": [],
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
    """Issue 2: 当 _long_term 为 None 但有 knowledge/work/history items 时，不应清理短期记忆。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        # _long_term = None
        dm = DreamManager(Path(d), stm, long_term=None, user_manager=um)

        stm.add_item("有价值的知识", "pref_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": [],
            "knowledge": ["有价值的知识"],
            "work": [],
            "history": [],
            "soul": [],
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # _long_term 为 None 但 knowledge 非空 => 应视为写入失败
        assert len(stm.get_by_session("sess-1")) > 0, \
            "long_term 不可用时有 knowledge items 应视为写入失败，不应清理短期记忆"
        assert dm._state["sessions_since_dream"] == 5, \
            "写入失败时不应推进 dream 状态"
        assert dm._state["total_dreams"] == 0, \
            "写入失败时不应递增 total_dreams"


def test_degraded_user_manager_none_prevents_cleanup():
    """Issue 2: 当 _user_manager 为 None 但有 user items 时，不应清理短期记忆。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        # _user_manager = None
        dm = DreamManager(Path(d), stm, long_term=ltm, user_manager=None)

        stm.add_item("核心记忆", "pref_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": ["核心记忆"],
            "knowledge": [],
            "work": [],
            "history": [],
            "soul": [],
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # _user_manager 为 None 但 user 非空 => 应视为写入失败
        assert len(stm.get_by_session("sess-1")) > 0, \
            "user_manager 不可用时有 user items 应视为写入失败，不应清理短期记忆"
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

        stm.add_item("一些内容", "pref_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": ["核心"],
            "knowledge": ["知识"],
            "work": [],
            "history": [],
            "soul": [],
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        assert len(stm.get_by_session("sess-1")) > 0, \
            "所有 sink 不可用时不应清理短期记忆"


def test_all_discard_with_no_sinks_still_cleans():
    """Issue 2: 当所有 items 都是 discard 且没有其他类 items 时，即使 sink 为 None 也可以安全清理。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        dm = DreamManager(Path(d), stm, long_term=None, user_manager=None)

        stm.add_item("垃圾信息", "pref_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": [],
            "knowledge": [],
            "work": [],
            "history": [],
            "soul": [],
            "discard": ["垃圾信息"],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 全部 discard，不需要写入任何 sink，可以安全清理
        assert dm._state["total_dreams"] == 1, \
            "全部 discard 时应正常完成 dream"


# === Milestone 22: 五路径分类改造 ===


def test_validate_classification_six_key_structure():
    """五路径: _validate_classification 应返回 6-key 结构 (user, knowledge, work, history, soul, discard)。"""
    from memory.dream import DreamManager

    result = {
        "user": ["用户是创业者"],
        "knowledge": ["Python 是解释型语言"],
        "work": ["项目 deadline 下周五"],
        "history": ["去年去了日本旅行"],
        "soul": ["性格偏内向"],
        "discard": ["天气不错"],
    }
    validated = DreamManager._validate_classification(result)

    assert "user" in validated, "应包含 user key"
    assert "knowledge" in validated, "应包含 knowledge key"
    assert "work" in validated, "应包含 work key"
    assert "history" in validated, "应包含 history key"
    assert "soul" in validated, "应包含 soul key"
    assert "discard" in validated, "应包含 discard key"
    # 旧结构不应存在
    assert "core" not in validated, "不应包含旧的 core key"
    assert "topics" not in validated, "不应包含旧的 topics key"


def test_validate_classification_filters_non_string_entries():
    """五路径: _validate_classification 应过滤非字符串条目。"""
    from memory.dream import DreamManager

    result = {
        "user": ["valid user", 123, None],
        "knowledge": [456, "valid knowledge"],
        "work": ["valid work", {"nested": "dict"}],
        "history": ["valid history"],
        "soul": [None, "valid soul"],
        "discard": ["valid discard", []],
    }
    validated = DreamManager._validate_classification(result)

    assert validated["user"] == ["valid user"]
    assert validated["knowledge"] == ["valid knowledge"]
    assert validated["work"] == ["valid work"]
    assert validated["history"] == ["valid history"]
    assert validated["soul"] == ["valid soul"]
    assert validated["discard"] == ["valid discard"]


def test_validate_classification_handles_missing_keys():
    """五路径: _validate_classification 缺少某些 key 时应返回空列表。"""
    from memory.dream import DreamManager

    result = {"user": ["信息"]}
    validated = DreamManager._validate_classification(result)

    assert validated["user"] == ["信息"]
    assert validated["knowledge"] == []
    assert validated["work"] == []
    assert validated["history"] == []
    assert validated["soul"] == []
    assert validated["discard"] == []


def test_items_text_includes_type_and_category():
    """五路径: items_text 格式应包含 type 和 category 信息。"""
    from memory.dream import DreamManager

    dm = DreamManager(Path(tempfile.mkdtemp()))

    items = [
        {"content": "在家办公", "type": "preference", "category": "user"},
        {"content": "用户是创业者", "type": "fact", "category": "user"},
        {"content": "Python 很好用", "type": "fact", "category": ""},
    ]

    items_text = dm._format_items_text(items)

    assert "- [preference/user] 在家办公" in items_text
    assert "- [fact/user] 用户是创业者" in items_text
    assert "- [fact/] Python 很好用" in items_text


def test_items_text_fallback_without_type_category():
    """五路径: items 缺少 type/category 字段时应降级到 source。"""
    from memory.dream import DreamManager

    dm = DreamManager(Path(tempfile.mkdtemp()))

    items = [
        {"content": "一些内容", "source": "pref_detection"},
    ]

    items_text = dm._format_items_text(items)

    assert "- [pref_detection] 一些内容" in items_text


def test_run_writes_user_items_to_user_manager():
    """五路径: user 类 items 应写入 user_manager。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        stm.add_item("用户是创业者", "pref_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": ["用户是创业者"],
            "knowledge": [],
            "work": [],
            "history": [],
            "soul": [],
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        user_content = um.load()
        assert "用户是创业者" in user_content, "user items 应写入 user.md"


def test_run_writes_knowledge_items_to_long_term():
    """五路径: knowledge 类 items 应写入 knowledge.md。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        stm.add_item("Python 是解释型语言", "fact_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": [],
            "knowledge": ["Python 是解释型语言"],
            "work": [],
            "history": [],
            "soul": [],
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        content = ltm.read_topic("knowledge.md")
        assert "Python 是解释型语言" in content, "knowledge items 应写入 knowledge.md"


def test_run_writes_work_items_to_long_term():
    """五路径: work 类 items 应写入 work.md。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        stm.add_item("项目 deadline 下周五", "event_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": [],
            "knowledge": [],
            "work": ["项目 deadline 下周五"],
            "history": [],
            "soul": [],
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        content = ltm.read_topic("work.md")
        assert "项目 deadline 下周五" in content, "work items 应写入 work.md"


def test_run_writes_history_items_to_long_term():
    """五路径: history 类 items 应写入 history.md。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        stm.add_item("去年去了日本旅行", "event_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": [],
            "knowledge": [],
            "work": [],
            "history": ["去年去了日本旅行"],
            "soul": [],
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        content = ltm.read_topic("history.md")
        assert "去年去了日本旅行" in content, "history items 应写入 history.md"


def test_run_writes_soul_items_to_soul_manager():
    """五路径: soul 类 items 应写入 soul_manager（经 LLM 提炼）。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um, soul_manager=sm)

        stm.add_item("性格偏内向", "reflection_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        # run() 现在调用两次 LLM：分类 + soul 演化
        mock_llm.chat.side_effect = [
            MagicMock(content=json.dumps({
                "user": [],
                "knowledge": [],
                "work": [],
                "history": [],
                "soul": ["性格偏内向"],
                "discard": [],
            })),
            MagicMock(content="性格倾向：偏内向"),
        ]

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        soul_content = sm.load_growth()
        assert "偏内向" in soul_content, "soul items 应经 LLM 提炼后通过 soul_manager 写入"


def test_degraded_soul_manager_none_prevents_cleanup():
    """五路径: soul_manager 为 None 但有 soul items 时应视为写入失败。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        # soul_manager=None
        dm = DreamManager(Path(d), stm, ltm, um, soul_manager=None)

        stm.add_item("性格偏内向", "reflection_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": [],
            "knowledge": [],
            "work": [],
            "history": [],
            "soul": ["性格偏内向"],
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # soul_manager 为 None 但有 soul items => 写入失败
        assert len(stm.get_by_session("sess-1")) > 0, \
            "soul_manager 不可用时有 soul items 应视为写入失败"
        assert dm._state["sessions_since_dream"] == 5, \
            "写入失败时不应推进 dream 状态"


def test_five_path_run_mixed_all_sinks():
    """五路径: 混合场景 — user/knowledge/work/history/soul/discard 各有 items，全部写入正确 sink。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um, soul_manager=sm)

        stm.add_item("混合测试", "pref_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        # run() 现在调用两次 LLM：分类 + soul 演化
        mock_llm.chat.side_effect = [
            MagicMock(content=json.dumps({
                "user": ["用户喜欢咖啡"],
                "knowledge": ["Python 是解释型语言"],
                "work": ["项目 deadline 下周五"],
                "history": ["去年去了日本"],
                "soul": ["容易焦虑"],
                "discard": ["天气不错"],
            })),
            MagicMock(content="情绪基线：容易焦虑，需要关注"),
        ]

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 验证各 sink 接收到正确内容
        assert "用户喜欢咖啡" in um.load(), "user items 应写入 user.md"
        assert "Python 是解释型语言" in ltm.read_topic("knowledge.md"), "knowledge items 应写入 knowledge.md"
        assert "项目 deadline 下周五" in ltm.read_topic("work.md"), "work items 应写入 work.md"
        assert "去年去了日本" in ltm.read_topic("history.md"), "history items 应写入 history.md"
        assert "焦虑" in sm.load_growth(), "soul items 应经 LLM 提炼后写入 soul.md"

        # discard 不写入任何 sink，但 dream 应成功完成
        assert dm._state["total_dreams"] == 1, "混合场景应成功完成 dream"


# === CQR Fixes: Finding 1-4 ===


def test_write_to_long_term_uses_append_mode():
    """Finding 1: _write_to_long_term 应使用 append=True 模式，保留已有内容并追加新内容。"""
    from memory.dream import DreamManager
    from memory.long_term import LongTermMemory

    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        dm = DreamManager(Path(d), long_term=ltm)

        # 第一次写入
        dm._write_to_long_term("knowledge", ["Python 是解释型语言"])
        first_content = ltm.read_topic("knowledge.md")
        assert "Python 是解释型语言" in first_content

        # 第二次写入：应追加而非覆盖
        dm._write_to_long_term("knowledge", ["Go 是编译型语言"])
        second_content = ltm.read_topic("knowledge.md")
        assert "Python 是解释型语言" in second_content, \
            "第二次写入不应覆盖第一次的内容"
        assert "Go 是编译型语言" in second_content, \
            "第二次写入的内容应被追加"


def test_write_to_long_term_frontmatter_type_is_long_term():
    """Finding 1: _write_to_long_term 写入的 frontmatter type 应为 long_term 而非 user。"""
    from memory.dream import DreamManager
    from memory.long_term import LongTermMemory

    with tempfile.TemporaryDirectory() as d:
        ltm = LongTermMemory(Path(d))
        dm = DreamManager(Path(d), long_term=ltm)

        dm._write_to_long_term("knowledge", ["测试内容"])

        # 读取原始文件检查 frontmatter
        raw = (Path(d) / "long-term" / "knowledge.md").read_text(encoding="utf-8")
        assert 'type: long_term' in raw, \
            f"frontmatter type 应为 long_term，实际文件内容:\n{raw}"
        assert 'type: user' not in raw, \
            f"frontmatter type 不应为 user，实际文件内容:\n{raw}"


def test_empty_classification_does_not_delete_memory():
    """Finding 2 & 4: LLM 返回 {} 时，不应删除任何短期记忆，不应推进 dream 状态。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        stm.add_item("重要记忆", "pref_detection", session_id="sess-1")
        stm.add_item("另一条记忆", "fact_detection", session_id="sess-1")

        # mock LLM 返回空分类
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content="{}")

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._state["total_dreams"] = 2
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 短期记忆不应被删除
        remaining = stm.get_by_session("sess-1")
        assert len(remaining) >= 2, \
            f"空分类不应删除短期记忆，应至少剩 2 条，实际剩 {len(remaining)} 条"
        # dream 状态不应推进
        assert dm._state["sessions_since_dream"] == 5, \
            "空分类时 sessions_since_dream 应保持不变"
        assert dm._state["total_dreams"] == 2, \
            "空分类时 total_dreams 不应递增"


def test_all_empty_buckets_does_not_delete_memory():
    """Finding 2: 所有 bucket 为空但 discard 也为空时，不应删除短期记忆。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um)

        stm.add_item("重要内容", "pref_detection", session_id="sess-1")

        # mock LLM 返回所有 bucket 为空（含 discard）
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": [],
            "knowledge": [],
            "work": [],
            "history": [],
            "soul": [],
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._state["total_dreams"] = 1
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        remaining = stm.get_by_session("sess-1")
        assert len(remaining) >= 1, \
            f"所有 bucket 为空时不应删除短期记忆，实际剩 {len(remaining)} 条"
        assert dm._state["sessions_since_dream"] == 5, \
            "所有 bucket 为空时不应推进 dream 状态"
        assert dm._state["total_dreams"] == 1, \
            "所有 bucket 为空时 total_dreams 不应递增"


def test_soul_items_batched_before_save_growth():
    """Finding 3: soul items 应被合并后经 LLM 提炼写入（一次 _update_soul_growth 调用）。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um, soul_manager=sm)

        stm.add_item("混合测试", "pref_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        # run() 现在调用两次 LLM：分类 + soul 演化
        mock_llm.chat.side_effect = [
            MagicMock(content=json.dumps({
                "user": [],
                "knowledge": [],
                "work": [],
                "history": [],
                "soul": ["性格偏内向", "需要更多耐心"],
                "discard": [],
            })),
            MagicMock(content="性格倾向：偏内向但正在学习耐心"),
        ]

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # LLM 提炼后的结果应被写入
        soul_content = sm.load_growth()
        assert "偏内向" in soul_content, \
            f"soul 演化结果应在成长中，实际:\n{soul_content}"
        assert "耐心" in soul_content, \
            f"soul 演化结果应在成长中，实际:\n{soul_content}"


# === Task 3: _update_soul_growth 人格演化逻辑 ===


def test_update_soul_growth_calls_llm_with_existing_growth():
    """_update_soul_growth 应读取现有成长内容并结合新 items 发送给 LLM 做提炼。"""
    from memory.dream import DreamManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), soul_manager=sm)

        # 预设已有成长内容
        sm.save_growth("性格偏内向")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(
            content="性格偏内向，近期变得更加耐心"
        )

        asyncio.run(dm._update_soul_growth(mock_llm, "test/model", ["变得更加耐心"]))

        # LLM 应被调用一次
        assert mock_llm.chat.call_count == 1, "应调用 LLM 一次"
        # prompt 应包含已有成长内容
        call_args = mock_llm.chat.call_args
        prompt_text = call_args.kwargs["messages"][1]["content"]
        assert "性格偏内向" in prompt_text, \
            f"prompt 应包含已有成长内容，实际 prompt:\n{prompt_text}"
        assert "变得更加耐心" in prompt_text, \
            f"prompt 应包含新 soul items，实际 prompt:\n{prompt_text}"


def test_update_soul_growth_saves_llm_output():
    """_update_soul_growth 应将 LLM 提炼后的内容通过 save_growth 写入。"""
    from memory.dream import DreamManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), soul_manager=sm)

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(
            content="性格偏内向，近期在学习耐心"
        )

        asyncio.run(dm._update_soul_growth(mock_llm, "test/model", ["学习耐心"]))

        growth = sm.load_growth()
        assert "学习耐心" in growth, \
            f"LLM 输出应被 save_growth 写入，实际成长内容:\n{growth}"


def test_update_soul_growth_empty_existing():
    """_update_soul_growth 无已有成长内容时，应仅基于新 items 做提炼。"""
    from memory.dream import DreamManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), soul_manager=sm)

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(
            content="初识印象：用户偏好直接沟通"
        )

        asyncio.run(dm._update_soul_growth(mock_llm, "test/model", ["用户偏好直接沟通"]))

        # LLM 应被调用
        assert mock_llm.chat.call_count == 1
        growth = sm.load_growth()
        assert "直接沟通" in growth, \
            f"首次成长内容应被写入，实际:\n{growth}"


def test_update_soul_growth_llm_failure_propagates():
    """_update_soul_growth LLM 调用失败时应抛出异常。"""
    from memory.dream import DreamManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), soul_manager=sm)

        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = RuntimeError("LLM 连接超时")

        with pytest.raises(RuntimeError, match="LLM 连接超时"):
            asyncio.run(dm._update_soul_growth(mock_llm, "test/model", ["测试"]))


def test_update_soul_growth_independent_llm_call():
    """_update_soul_growth 的 LLM 调用应独立于分类调用（不同 prompt、不同 role 设置）。"""
    from memory.dream import DreamManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), soul_manager=sm)

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(
            content="人格演化结果"
        )

        asyncio.run(dm._update_soul_growth(mock_llm, "test/model", ["测试项"]))

        # 检查 system message 不是分类助手
        call_args = mock_llm.chat.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "分类" not in system_msg, \
            f"soul 演化的 system prompt 不应是分类助手，实际:\n{system_msg}"


def test_update_soul_growth_merges_and_refines():
    """_update_soul_growth 应将新旧内容合并后交给 LLM 做趋势提炼，而非简单追加。"""
    from memory.dream import DreamManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), soul_manager=sm)

        # 预设已有成长内容
        sm.save_growth("用户近期情绪稳定")

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(
            content="性格倾向：用户近期情绪稳定，但工作压力导致偶尔焦虑"
        )

        asyncio.run(dm._update_soul_growth(
            mock_llm, "test/model",
            ["工作压力大", "偶尔感到焦虑"],
        ))

        growth = sm.load_growth()
        # LLM 提炼后的结果应被保存（不是简单追加原始 items）
        assert "焦虑" in growth, \
            f"LLM 提炼结果应被保存，实际:\n{growth}"


def test_run_calls_update_soul_growth_instead_of_direct_save():
    """run() 中 soul 路径应调用 _update_soul_growth，而非直接 save_growth。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um, soul_manager=sm)

        stm.add_item("性格偏内向", "reflection_detection", session_id="sess-1")

        # run() 会调用两次 LLM：分类 + soul 演化
        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = [
            # 第一次：分类
            MagicMock(content=json.dumps({
                "user": [],
                "knowledge": [],
                "work": [],
                "history": [],
                "soul": ["性格偏内向"],
                "discard": [],
            })),
            # 第二次：soul 演化提炼
            MagicMock(content="性格倾向：偏内向，但近期社交能力有所提升"),
        ]

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # LLM 应被调用两次（分类 + soul 演化）
        assert mock_llm.chat.call_count == 2, \
            f"run() 应调用 LLM 两次（分类 + soul 演化），实际调用 {mock_llm.chat.call_count} 次"
        # 成长内容应是 LLM 提炼后的结果
        growth = sm.load_growth()
        assert "内向" in growth, \
            f"soul 演化结果应被写入，实际:\n{growth}"


def test_run_soul_evolution_failure_blocks_cleanup():
    """run() 中 soul 演化 LLM 调用失败时，不应清理短期记忆。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um, soul_manager=sm)

        stm.add_item("性格偏内向", "reflection_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = [
            # 第一次：分类成功
            MagicMock(content=json.dumps({
                "user": [],
                "knowledge": [],
                "work": [],
                "history": [],
                "soul": ["性格偏内向"],
                "discard": [],
            })),
            # 第二次：soul 演化 LLM 失败
            RuntimeError("LLM 调用失败"),
        ]

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 演化失败应被视为写入失败，不应清理短期记忆
        assert len(stm.get_by_session("sess-1")) > 0, \
            "soul 演化失败时不应清理短期记忆"
        assert dm._state["sessions_since_dream"] == 5, \
            "soul 演化失败时不应推进 dream 状态"


def test_run_no_soul_items_skips_soul_llm():
    """run() 中无 soul items 时，不应调用 soul 演化 LLM。"""
    from memory.dream import DreamManager
    from memory.short_term import ShortTermMemory
    from memory.long_term import LongTermMemory
    from memory.user import UserMemoryManager
    from memory.soul import SoulManager

    with tempfile.TemporaryDirectory() as d:
        stm = ShortTermMemory(Path(d))
        ltm = LongTermMemory(Path(d))
        um = UserMemoryManager(Path(d))
        sm = SoulManager(Path(d))
        dm = DreamManager(Path(d), stm, ltm, um, soul_manager=sm)

        stm.add_item("测试", "pref_detection", session_id="sess-1")

        mock_llm = AsyncMock()
        # 只有分类调用，无 soul items
        mock_llm.chat.return_value = MagicMock(content=json.dumps({
            "user": ["测试用户"],
            "knowledge": [],
            "work": [],
            "history": [],
            "soul": [],
            "discard": [],
        }))

        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        # 只应调用一次 LLM（分类），不应有第二次（soul 演化）
        assert mock_llm.chat.call_count == 1, \
            f"无 soul items 时不应调用 soul 演化 LLM，实际调用 {mock_llm.chat.call_count} 次"
