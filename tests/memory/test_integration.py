"""集成测试 — 验证记忆系统完整链路。

覆盖链路：
1. add_item → get_recent → get_summary → system prompt 注入
2. 旧格式（UUID 命名）文件迁移 → 端到端可读
3. LongTermMemory 分类文件 → 索引 → 搜索 → system prompt
4. BrixMemoryProvider 完整链路（short_term_summary → system prompt）
5. Dream 蒸馏 → 长期记忆 → 搜索
6. 人格演化：emotion + reflection → Dream 分类 (soul) → 提炼 → soul.md growth → system prompt <soul> 注入
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ============================================================
# 1. 完整链路：add_item → get_recent → get_summary → system prompt
# ============================================================


class TestShortTermToSystemPrompt:
    """短期记忆写入 → 读取 → 摘要 → system prompt 注入完整链路。"""

    def test_add_item_to_system_prompt_full_chain(self):
        """add_item → get_recent → get_summary → build_system_prompt 注入。"""
        from memory.short_term import ShortTermMemory
        from memory.soul import SoulManager
        from memory.user import UserMemoryManager
        from memory.strategy import MemoryStrategy

        with tempfile.TemporaryDirectory() as d:
            data_dir = Path(d)
            stm = ShortTermMemory(data_dir)
            soul = SoulManager(data_dir)
            user = UserMemoryManager(data_dir)

            # 写入 soul 和 user 以跳过 onboarding
            soul.save("# Soul\nI am Brix.")
            user.save("# User\nName: test")

            # 写入短期记忆
            stm.add_item(
                content="用户喜欢中餐，尤其是川菜",
                source="pref_detection",
                date="2026-06-06",
                type="preference",
                category="饮食",
                session_id="sess-integration",
                context="用户说要吃爆炒腊肉",
            )
            stm.add_item(
                content="用户是一名 Python 开发者",
                source="pref_detection",
                date="2026-06-06",
                type="fact",
                category="背景",
                session_id="sess-integration",
                context="用户提到日常写 Python",
            )

            # 链路 1：get_recent 应返回 2 条
            items = stm.get_recent(limit=10)
            assert len(items) == 2

            # 链路 2：get_summary 应包含格式化文本
            summary = stm.get_summary(limit=10)
            assert summary is not None
            assert "用户喜欢中餐" in summary
            assert "Python 开发者" in summary
            assert "[preference]" in summary
            assert "[fact]" in summary
            assert "2026-06-06" in summary

            # 链路 3：build_system_prompt 注入 short_term_summary
            strategy = MemoryStrategy(
                soul_manager=soul, user_manager=user, max_tokens=8000
            )
            prompt = strategy.build_system_prompt(short_term_summary=summary)
            assert "用户喜欢中餐" in prompt
            assert "Python 开发者" in prompt
            assert "<short_term_memory>" in prompt

    def test_summary_with_type_and_timestamp_format(self):
        """get_summary 输出格式：- [Weekday YYYY-MM-DD HH:MM] [{type}] {content}。"""
        from memory.short_term import ShortTermMemory

        with tempfile.TemporaryDirectory() as d:
            stm = ShortTermMemory(Path(d))
            # 写入并手动设置 created 时间以确保输出可预测
            stm.add_item(
                content="用户偏好红茶",
                source="tool",
                date="2026-06-06",
                type="preference",
            )
            # 手动设置 created 为已知 UTC 时间
            f = Path(d) / "short-term" / "2026-06-06.json"
            data = json.loads(f.read_text(encoding="utf-8"))
            data["items"][0]["created"] = "2026-06-06T09:30:00+00:00"
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            summary = stm.get_summary(limit=10)
            assert summary is not None
            # 应包含 [preference] 标签
            assert "[preference]" in summary
            # 应包含日期
            assert "2026-06-06" in summary
            # 应包含内容
            assert "用户偏好红茶" in summary

    def test_empty_short_term_returns_none_summary(self):
        """无短期记忆时 get_summary 返回 None，system prompt 无 <short_term_memory>。"""
        from memory.short_term import ShortTermMemory
        from memory.soul import SoulManager
        from memory.user import UserMemoryManager
        from memory.strategy import MemoryStrategy

        with tempfile.TemporaryDirectory() as d:
            data_dir = Path(d)
            stm = ShortTermMemory(data_dir)
            soul = SoulManager(data_dir)
            user = UserMemoryManager(data_dir)
            soul.save("# Soul")
            user.save("# User")

            summary = stm.get_summary(limit=10)
            assert summary is None

            strategy = MemoryStrategy(
                soul_manager=soul, user_manager=user
            )
            prompt = strategy.build_system_prompt()
            assert "<short_term_memory>" not in prompt


# ============================================================
# 2. 旧格式（UUID）文件迁移 → 端到端
# ============================================================


class TestLegacyMigrationEndToEnd:
    """旧格式 UUID 文件迁移后应可被完整链路读取。"""

    def test_legacy_file_migrated_and_visible_in_summary(self):
        """旧格式 UUID 文件 → 迁移 → get_recent → get_summary → system prompt。"""
        from memory.short_term import ShortTermMemory
        from memory.soul import SoulManager
        from memory.user import UserMemoryManager
        from memory.strategy import MemoryStrategy

        with tempfile.TemporaryDirectory() as d:
            data_dir = Path(d)
            stm = ShortTermMemory(data_dir)
            soul = SoulManager(data_dir)
            user = UserMemoryManager(data_dir)
            soul.save("# Soul")
            user.save("# User")

            # 写入旧格式文件（UUID 命名）
            date_dir = data_dir / "short-term"
            date_dir.mkdir(parents=True, exist_ok=True)
            legacy_data = {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "items": [
                    {
                        "id": "legacy-item-1",
                        "content": "用户来自上海",
                        "source": "pref_detection",
                        "type": "fact",
                        "category": "背景",
                        "session_id": "550e8400-e29b-41d4-a716-446655440000",
                        "created": "2026-06-05T14:00:00+00:00",
                        "context": "用户提到住在上海",
                    },
                    {
                        "id": "legacy-item-2",
                        "content": "用户喜欢跑步",
                        "source": "pref_detection",
                        "type": "preference",
                        "category": "运动",
                        "session_id": "550e8400-e29b-41d4-a716-446655440000",
                        "created": "2026-06-05T15:00:00+00:00",
                        "context": "用户说经常晨跑",
                    },
                ],
            }
            legacy_file = date_dir / "550e8400-e29b-41d4-a716-446655440000.json"
            legacy_file.write_text(
                json.dumps(legacy_data, ensure_ascii=False), encoding="utf-8"
            )

            # 链路 1：get_recent 触发迁移
            items = stm.get_recent(limit=10)
            assert len(items) == 2
            contents = {i["content"] for i in items}
            assert "用户来自上海" in contents
            assert "用户喜欢跑步" in contents

            # 旧文件已删除，日期文件已创建
            assert not legacy_file.exists()
            date_file = date_dir / "2026-06-05.json"
            assert date_file.exists()

            # 链路 2：get_summary 包含迁移后的数据
            summary = stm.get_summary(limit=10)
            assert summary is not None
            assert "用户来自上海" in summary
            assert "用户喜欢跑步" in summary

            # 链路 3：system prompt 注入
            strategy = MemoryStrategy(
                soul_manager=soul, user_manager=user
            )
            prompt = strategy.build_system_prompt(short_term_summary=summary)
            assert "用户来自上海" in prompt
            assert "<short_term_memory>" in prompt

    def test_legacy_file_with_mixed_dates_migrates_to_correct_buckets(self):
        """旧格式文件含多个日期的 items → 迁移到对应日期 bucket。"""
        from memory.short_term import ShortTermMemory

        with tempfile.TemporaryDirectory() as d:
            stm = ShortTermMemory(Path(d))
            date_dir = Path(d) / "short-term"
            date_dir.mkdir(parents=True, exist_ok=True)

            legacy_data = {
                "items": [
                    {
                        "id": "item-day1",
                        "content": "第一天的记忆",
                        "source": "test",
                        "type": "note",
                        "category": "",
                        "session_id": "old-sess",
                        "created": "2026-06-01T10:00:00+00:00",
                        "context": "",
                    },
                    {
                        "id": "item-day2",
                        "content": "第二天的记忆",
                        "source": "test",
                        "type": "note",
                        "category": "",
                        "session_id": "old-sess",
                        "created": "2026-06-02T10:00:00+00:00",
                        "context": "",
                    },
                    {
                        "id": "item-day3",
                        "content": "第三天的记忆",
                        "source": "test",
                        "type": "note",
                        "category": "",
                        "session_id": "old-sess",
                        "created": "2026-06-03T10:00:00+00:00",
                        "context": "",
                    },
                ],
            }
            (date_dir / "a1b2c3d4-e5f6-7890-abcd-ef1234567890.json").write_text(
                json.dumps(legacy_data, ensure_ascii=False), encoding="utf-8"
            )

            # get_recent 触发迁移
            items = stm.get_recent(limit=10)
            assert len(items) == 3

            # 每个日期 bucket 应有对应文件
            assert (date_dir / "2026-06-01.json").exists()
            assert (date_dir / "2026-06-02.json").exists()
            assert (date_dir / "2026-06-03.json").exists()

            # get_by_date 能读取迁移后的数据
            day1 = stm.get_by_date("2026-06-01")
            assert len(day1) == 1
            assert day1[0]["content"] == "第一天的记忆"

            day2 = stm.get_by_date("2026-06-02")
            assert len(day2) == 1
            assert day2[0]["content"] == "第二天的记忆"


# ============================================================
# 3. LongTermMemory 分类文件 → 索引 → 搜索
# ============================================================


class TestLongTermCategoryEndToEnd:
    """LongTermMemory 分类文件完整链路：写入 → 索引 → 搜索。"""

    def test_category_files_visible_in_search(self):
        """分类文件写入 → update_index → 搜索可命中。"""
        from memory.long_term import LongTermMemory
        from memory.searcher import KeywordMemorySearcher

        with tempfile.TemporaryDirectory() as d:
            ltm = LongTermMemory(Path(d))
            fm = {
                "name": "用户画像",
                "description": "用户核心信息",
                "type": "long_term",
            }

            # 写入分类文件
            ltm.write_topic(
                "user.md",
                "用户喜欢中餐，尤其是川菜\n用户来自上海",
                fm,
                append=True,
            )
            ltm.write_topic(
                "work.md",
                "用户是一名 Python 开发者\n日常使用 pytest 做测试",
                {"name": "工作上下文", "description": "工作相关", "type": "long_term"},
                append=True,
            )
            ltm.update_index()

            # 索引应包含两个分类文件
            topics = ltm.list_topics()
            indexed_files = {t["file"] for t in topics}
            assert "user.md" in indexed_files
            assert "work.md" in indexed_files

            # 搜索应命中
            searcher = KeywordMemorySearcher(ltm, short_term=None)
            results = searcher.search("川菜")
            assert len(results) > 0
            assert "川" in results[0].content

            results = searcher.search("Python")
            assert len(results) > 0
            assert "Python" in results[0].content

    def test_category_plus_topic_files_in_search(self):
        """分类文件 + 非分类 topic 文件都应可搜索。"""
        from memory.long_term import LongTermMemory
        from memory.searcher import KeywordMemorySearcher

        with tempfile.TemporaryDirectory() as d:
            ltm = LongTermMemory(Path(d))
            fm = {"name": "测试", "description": "测试", "type": "long_term"}

            # 分类文件
            ltm.write_topic("user.md", "用户喜欢咖啡", fm)
            # 非分类 topic 文件（模拟 dream 写入）
            ltm.write_topic("coffee_interests.md", "用户偏好手冲咖啡", fm)
            ltm.update_index()

            searcher = KeywordMemorySearcher(ltm, short_term=None)
            results = searcher.search("咖啡")
            assert len(results) >= 2  # 两个文件都应命中
            contents = " ".join(r.content for r in results)
            assert "喜欢咖啡" in contents or "手冲咖啡" in contents

    def test_long_term_and_short_term_combined_search(self):
        """长期 + 短期记忆联合搜索。"""
        from memory.long_term import LongTermMemory
        from memory.short_term import ShortTermMemory
        from memory.searcher import KeywordMemorySearcher

        with tempfile.TemporaryDirectory() as d:
            ltm = LongTermMemory(Path(d))
            stm = ShortTermMemory(Path(d))

            # 长期记忆
            fm = {"name": "用户画像", "description": "描述", "type": "long_term"}
            ltm.write_topic("user.md", "用户喜欢中餐", fm)
            ltm.update_index()

            # 短期记忆
            stm.add_item(
                "用户今天吃了火锅",
                "session_summary",
                date="2026-06-06",
                type="event",
            )

            searcher = KeywordMemorySearcher(ltm, short_term=stm)
            results = searcher.search("中餐")
            # 应命中长期记忆
            assert any(r.source == "long_term" for r in results)

            results = searcher.search("火锅")
            # 应命中短期记忆
            assert any(r.source == "short_term" for r in results)


# ============================================================
# 4. BrixMemoryProvider 完整链路
# ============================================================


class TestProviderEndToEnd:
    """BrixMemoryProvider 完整链路：short_term_summary → build_system_prompt。"""

    def test_provider_get_short_term_summary_and_inject(self):
        """BrixMemoryProvider.get_short_term_summary → build_system_prompt(short_term_summary=...)。"""
        from memory.provider import BrixMemoryProvider

        with tempfile.TemporaryDirectory() as d:
            data_dir = Path(d)
            provider = BrixMemoryProvider(data_dir=data_dir)

            # 写入 soul/user 跳过 onboarding
            provider._soul.save("# Soul")
            provider._user.save("# User")

            # 通过 short_term 组件写入记忆
            assert provider.short_term is not None
            provider.short_term.add_item(
                content="用户喜欢喝茶",
                source="pref_detection",
                date="2026-06-06",
                type="preference",
                session_id="test-sess",
            )

            # 获取摘要
            summary = provider.get_short_term_summary(limit=10)
            assert summary is not None
            assert "用户喜欢喝茶" in summary

            # 构建 system prompt 并注入
            prompt = provider.build_system_prompt(short_term_summary=summary)
            assert "用户喜欢喝茶" in prompt
            assert "<short_term_memory>" in prompt

    def test_provider_full_message_flow_with_memory(self):
        """add_message + add_full_message + save → 持久化可读。"""
        from memory.provider import BrixMemoryProvider

        with tempfile.TemporaryDirectory() as d:
            provider = BrixMemoryProvider(data_dir=Path(d))

            # 普通消息
            provider.add_message("user", "你好")
            provider.add_message("assistant", "你好！有什么可以帮你的？")

            # 带 tool_calls 的完整消息
            provider.add_full_message({
                "role": "assistant",
                "content": "让我帮你查一下。",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search", "arguments": '{"q": "test"}'},
                    }
                ],
            })
            provider.add_full_message({
                "role": "tool",
                "tool_call_id": "call_1",
                "name": "search",
                "content": "search result",
            })

            provider.save_session()

            # 验证持久化
            sessions = provider.list_sessions()
            assert len(sessions) == 1
            sid = sessions[0]["id"]

            loaded = provider.load_session(sid)
            assert len(loaded) == 4
            # 第三条应有 tool_calls
            assert loaded[2]["tool_calls"][0]["id"] == "call_1"
            # 第四条应是 tool result
            assert loaded[3]["role"] == "tool"

    def test_provider_resume_session_preserves_memory_context(self):
        """resume session 后 add_message 应写入恢复的 session。"""
        from memory.provider import BrixMemoryProvider

        with tempfile.TemporaryDirectory() as d:
            provider = BrixMemoryProvider(data_dir=Path(d))

            # 第一个 session
            provider.add_message("user", "第一条消息")
            provider.save_session()
            first_sid = provider.current_session_id

            # 第二个 session
            provider.create_session()
            provider.add_message("user", "第二条消息")
            provider.save_session()

            # 恢复第一个 session
            messages = provider.resume_session(first_sid)
            assert len(messages) == 1
            assert messages[0]["content"] == "第一条消息"

            # 在恢复的 session 中添加消息
            provider.add_message("user", "恢复后的消息")
            provider.save_session()

            # 验证
            loaded = provider.load_session(first_sid)
            assert len(loaded) == 2
            assert loaded[1]["content"] == "恢复后的消息"


# ============================================================
# 5. Dream 蒸馏 → 长期记忆 → 搜索链路
# ============================================================


class TestDreamDistillationEndToEnd:
    """Dream 蒸馏完整链路：短期记忆 → LLM 分类 → 写入长期记忆/核心记忆 → 可搜索。"""

    def test_dream_writes_to_long_term_and_searchable(self):
        """Dream 蒸馏写入长期记忆后，搜索应能找到。"""
        import asyncio
        from memory.dream import DreamManager
        from memory.short_term import ShortTermMemory
        from memory.long_term import LongTermMemory
        from memory.user import UserMemoryManager
        from memory.searcher import KeywordMemorySearcher

        with tempfile.TemporaryDirectory() as d:
            stm = ShortTermMemory(Path(d))
            ltm = LongTermMemory(Path(d))
            um = UserMemoryManager(Path(d))
            dm = DreamManager(Path(d), stm, ltm, um)

            # 写入短期记忆
            stm.add_item(
                "用户喜欢手冲咖啡",
                "pref_detection",
                session_id="sess-coffee",
            )
            stm.add_item(
                "用户常用 Vim 编辑器",
                "pref_detection",
                session_id="sess-vim",
            )

            # mock LLM 分类（6-key 五路径格式）
            mock_llm = AsyncMock()
            mock_llm.chat.return_value = MagicMock(
                content=json.dumps(
                    {
                        "user": ["用户喜欢手冲咖啡"],
                        "knowledge": ["用户常用 Vim 编辑器"],
                        "work": [],
                        "history": [],
                        "soul": [],
                        "discard": [],
                    }
                )
            )

            # 触发 dream
            dm._state["last_dream_at"] = (
                datetime.now(timezone.utc) - timedelta(hours=25)
            ).isoformat()
            dm._state["sessions_since_dream"] = 5
            dm._save_state()

            asyncio.run(dm.run(mock_llm, "test/model"))

            # 验证：user 写入 user.md
            user_content = um.load()
            assert "用户喜欢手冲咖啡" in user_content

            # 验证：knowledge 写入 knowledge.md
            topic_content = ltm.read_topic("knowledge.md")
            assert "用户常用 Vim 编辑器" in topic_content

            # 验证：搜索可命中
            searcher = KeywordMemorySearcher(ltm, short_term=stm)
            results = searcher.search("Vim")
            assert any("Vim" in r.content for r in results)

    def test_dream_state_file_is_resilient(self):
        """Dream state 文件损坏时应自动恢复。"""
        from memory.dream import DreamManager

        with tempfile.TemporaryDirectory() as d:
            # 写入损坏的 state
            dream_dir = Path(d) / "dream"
            dream_dir.mkdir(parents=True, exist_ok=True)
            (dream_dir / "dream-state.json").write_text("not json", encoding="utf-8")

            # 不应崩溃
            dm = DreamManager(Path(d))
            assert dm.should_dream() is False  # 恢复为初始状态


# ============================================================
# 6. 人格演化链路：emotion + reflection → soul growth → system prompt
# ============================================================


class TestPersonalityEvolutionEndToEnd:
    """人格演化完整链路：emotion + reflection items → Dream 分类 (soul)
    → _update_soul_growth() → soul.md growth section → build_system_prompt() <soul> 注入。"""

    def test_personality_evolution_chain(self):
        """emotion + reflection → soul 分类 → LLM 提炼 → soul.md growth → system prompt <soul> 标签。"""
        import asyncio
        from memory.dream import DreamManager
        from memory.short_term import ShortTermMemory
        from memory.long_term import LongTermMemory
        from memory.soul import SoulManager
        from memory.user import UserMemoryManager
        from memory.strategy import MemoryStrategy

        with tempfile.TemporaryDirectory() as d:
            data_dir = Path(d)
            stm = ShortTermMemory(data_dir)
            ltm = LongTermMemory(data_dir)
            um = UserMemoryManager(data_dir)
            sm = SoulManager(data_dir)
            dm = DreamManager(data_dir, stm, ltm, um, soul_manager=sm)

            # 写入 soul.md 固定部分（模拟已有的人格定义）
            sm.save("# Soul — 固定部分\n\n## Core Personality\n直率、温暖、幽默")

            # 写入短期记忆：emotion + reflection 类型
            stm.add_item(
                "用户最近工作压力大，情绪低落",
                "emotion_detection",
                session_id="sess-emotion",
                type="emotion",
                category="情绪",
            )
            stm.add_item(
                "在回复用户时犯了一个错误，用户纠正了我，以后要更仔细核实信息",
                "reflection",
                session_id="sess-reflection",
                type="reflection",
                category="自我反思",
            )

            # Mock LLM：第一次调用 = 分类，第二次调用 = 灵魂提炼
            mock_llm = AsyncMock()
            # 第一次返回分类结果：soul 路径
            classification_response = MagicMock()
            classification_response.content = json.dumps({
                "user": [],
                "knowledge": [],
                "work": [],
                "history": [],
                "soul": [
                    "用户最近工作压力大，情绪低落",
                    "在回复用户时犯了一个错误，用户纠正了我，以后要更仔细核实信息",
                ],
                "discard": [],
            })
            # 第二次返回提炼后的成长内容
            growth_response = MagicMock()
            growth_response.content = (
                "情绪基线：用户近期工作压力较大，需要更多耐心和关怀。"
                "经验教训：被用户纠正后，认识到信息核实的重要性，"
                "以后在给出关键信息前应先确认准确性。"
            )
            mock_llm.chat.side_effect = [classification_response, growth_response]

            # 触发 dream（满足双门槛）
            dm._state["last_dream_at"] = (
                datetime.now(timezone.utc) - timedelta(hours=25)
            ).isoformat()
            dm._state["sessions_since_dream"] = 5
            dm._save_state()

            asyncio.run(dm.run(mock_llm, "test/model"))

            # 验证 1：soul.md growth section 包含提炼内容
            growth = sm.load_growth()
            assert "情绪基线" in growth
            assert "工作压力" in growth
            assert "信息核实" in growth

            # 验证 2：soul.md 固定部分未被修改
            fixed = sm.load_fixed()
            assert "直率、温暖、幽默" in fixed
            assert "Core Personality" in fixed

            # 验证 3：build_system_prompt() 的 <soul> 标签包含成长内容
            strategy = MemoryStrategy(
                soul_manager=sm, user_manager=um, max_tokens=8000
            )
            prompt = strategy.build_system_prompt()
            assert "<soul>" in prompt
            assert "</soul>" in prompt
            assert "情绪基线" in prompt
            assert "信息核实" in prompt
            # 固定部分也在 <soul> 标签内
            assert "直率、温暖、幽默" in prompt


# ============================================================
# 7. 端到端：记忆写入 → system prompt → 上下文窗口
# ============================================================


class TestContextWindowIntegration:
    """验证记忆写入后，上下文窗口正确包含 system prompt 和历史消息。"""

    def test_context_messages_include_system_prompt_with_memory(self):
        """记忆写入后，get_context_messages 返回的上下文应包含 system prompt 中的记忆。"""
        from memory.provider import BrixMemoryProvider

        with tempfile.TemporaryDirectory() as d:
            provider = BrixMemoryProvider(data_dir=Path(d))

            # 写入 soul 和 user
            provider._soul.save("# Soul\nI am Brix.")
            provider._user.save("# User\nName: tester")

            # 写入短期记忆
            assert provider.short_term is not None
            provider.short_term.add_item(
                "用户喜欢喝茶",
                "pref_detection",
                date="2026-06-06",
                type="preference",
            )

            # 获取摘要并构建 system prompt
            summary = provider.get_short_term_summary(limit=10)
            prompt = provider.build_system_prompt(short_term_summary=summary)

            # 添加会话消息
            provider.add_message("user", "你好")
            provider.add_message("assistant", "你好！有什么可以帮你的？")

            # 获取上下文消息
            context = provider.get_context_messages(prompt)
            assert len(context) >= 3  # system + 2 messages

            # system prompt 应包含记忆内容
            system_msg = context[0]
            assert system_msg["role"] == "system"
            assert "用户喜欢喝茶" in system_msg["content"]
            assert "<short_term_memory>" in system_msg["content"]

    def test_context_window_preserves_all_messages_within_budget(self):
        """在 token 预算内，所有消息都应保留。"""
        from memory.provider import BrixMemoryProvider

        with tempfile.TemporaryDirectory() as d:
            provider = BrixMemoryProvider(data_dir=Path(d), max_context_tokens=50000)
            provider._soul.save("# Soul")
            provider._user.save("# User")

            # 添加多条消息
            for i in range(10):
                provider.add_message("user", f"消息 {i}")
                provider.add_message("assistant", f"回复 {i}")

            prompt = provider.build_system_prompt()
            context = provider.get_context_messages(prompt)

            # 在大 token 预算下，所有消息都应保留
            non_system = [m for m in context if m["role"] != "system"]
            assert len(non_system) == 20
