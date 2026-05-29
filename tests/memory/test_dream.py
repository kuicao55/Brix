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
