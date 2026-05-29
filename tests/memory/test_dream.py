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

        # mock LLM
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = MagicMock(content="[]")

        # 需要手动设置状态使 should_dream 返回 True
        dm._state["last_dream_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        dm._state["sessions_since_dream"] = 5
        dm._save_state()

        asyncio.run(dm.run(mock_llm, "test/model"))

        state = dm._state
        assert state["sessions_since_dream"] == 0
        assert state["total_dreams"] == 1
