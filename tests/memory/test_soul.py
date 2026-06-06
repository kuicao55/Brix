"""SoulManager 测试 — 固定部分 + 成长部分格式改造。"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# ============================================================
# 1. load_fixed — 提取固定部分内容
# ============================================================

def test_load_fixed_full_soul():
    """有完整 soul.md（固定 + 成长）时，load_fixed 应只返回固定部分。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save(
            "# Soul — 固定部分\n"
            "我是用户的助手，保持专业和友好。\n"
            "\n"
            "# Soul — 成长部分\n"
            "## 性格倾向\n"
            "倾向于简洁回答\n"
        )
        fixed = sm.load_fixed()
        assert "固定部分" in fixed
        assert "我是用户的助手" in fixed
        assert "成长部分" not in fixed
        assert "性格倾向" not in fixed


def test_load_fixed_only_fixed_part():
    """soul.md 只有固定部分时，load_fixed 应返回全部内容。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save("# Soul — 固定部分\n我是用户的助手。\n")
        fixed = sm.load_fixed()
        assert "固定部分" in fixed
        assert "我是用户的助手" in fixed


def test_load_fixed_no_file():
    """soul.md 不存在时，load_fixed 应返回空字符串。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        assert sm.load_fixed() == ""


def test_load_fixed_old_format_without_headers():
    """旧格式 soul.md（无标题头）时，load_fixed 应返回空字符串。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save("我是旧格式的灵魂内容，没有标题头。\n")
        fixed = sm.load_fixed()
        assert fixed == ""


# ============================================================
# 2. load_growth — 提取成长部分内容
# ============================================================

def test_load_growth_full_soul():
    """有完整 soul.md（固定 + 成长）时，load_growth 应只返回成长部分。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save(
            "# Soul — 固定部分\n"
            "我是用户的助手。\n"
            "\n"
            "# Soul — 成长部分\n"
            "## 性格倾向\n"
            "倾向于简洁回答\n"
            "\n"
            "## 经验教训\n"
            "用户不喜欢冗长的解释\n"
        )
        growth = sm.load_growth()
        assert "固定部分" not in growth
        assert "我是用户的助手" not in growth
        assert "性格倾向" in growth
        assert "倾向于简洁回答" in growth
        assert "经验教训" in growth
        assert "用户不喜欢冗长的解释" in growth


def test_load_growth_only_growth_part():
    """soul.md 只有成长部分时（没有固定部分），load_growth 应返回成长内容。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save("# Soul — 成长部分\n## 性格倾向\n简洁\n")
        growth = sm.load_growth()
        assert "性格倾向" in growth
        assert "简洁" in growth


def test_load_growth_no_file():
    """soul.md 不存在时，load_growth 应返回空字符串。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        assert sm.load_growth() == ""


def test_load_growth_no_growth_section():
    """soul.md 只有固定部分没有成长部分时，load_growth 应返回空字符串。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save("# Soul — 固定部分\n我是用户的助手。\n")
        growth = sm.load_growth()
        assert growth == ""


def test_load_growth_old_format_without_headers():
    """旧格式 soul.md（无标题头）时，load_growth 应返回空字符串。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save("我是旧格式的灵魂内容。\n")
        growth = sm.load_growth()
        assert growth == ""


# ============================================================
# 3. save_growth — 只更新成长部分
# ============================================================

def test_save_growth_preserves_fixed():
    """save_growth 应保留固定部分不变，只更新成长部分。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save(
            "# Soul — 固定部分\n"
            "我是用户的助手。\n"
            "\n"
            "# Soul — 成长部分\n"
            "## 性格倾向\n"
            "旧的性格倾向\n"
        )
        sm.save_growth(
            "# Soul — 成长部分\n"
            "## 性格倾向\n"
            "新的性格倾向\n"
            "\n"
            "## 经验教训\n"
            "新的经验教训\n"
        )
        full = sm.load()
        assert "我是用户的助手" in full, "固定部分应保留"
        assert "新的性格倾向" in full, "成长部分应更新"
        assert "新的经验教训" in full, "成长部分应追加"
        assert "旧的性格倾向" not in full, "旧成长内容应被替换"


def test_save_growth_no_existing_growth():
    """soul.md 只有固定部分时，save_growth 应追加成长部分。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save("# Soul — 固定部分\n我是用户的助手。\n")
        sm.save_growth(
            "# Soul — 成长部分\n"
            "## 性格倾向\n"
            "简洁直接\n"
        )
        full = sm.load()
        assert "我是用户的助手" in full, "固定部分应保留"
        assert "性格倾向" in full, "成长部分应追加"
        assert "简洁直接" in full, "成长内容应存在"


def test_save_growth_no_file():
    """soul.md 不存在时，save_growth 应创建完整文件。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save_growth(
            "# Soul — 成长部分\n"
            "## 性格倾向\n"
            "简洁\n"
        )
        assert sm.exists()
        full = sm.load()
        assert "性格倾向" in full
        assert "简洁" in full


def test_save_growth_updates_only_growth():
    """多次 save_growth 应只影响成长部分，固定部分始终不变。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save(
            "# Soul — 固定部分\n"
            "永远保持尊重。\n"
            "\n"
            "# Soul — 成长部分\n"
            "## 情绪基线\n"
            "平静\n"
        )
        # 第一次更新
        sm.save_growth(
            "# Soul — 成长部分\n"
            "## 情绪基线\n"
            "积极\n"
        )
        assert "永远保持尊重" in sm.load()
        assert "积极" in sm.load()
        assert "平静" not in sm.load()

        # 第二次更新
        sm.save_growth(
            "# Soul — 成长部分\n"
            "## 性格倾向\n"
            "更直接\n"
            "\n"
            "## 情绪基线\n"
            "专注\n"
        )
        full = sm.load()
        assert "永远保持尊重" in full, "固定部分不受影响"
        assert "更直接" in full
        assert "专注" in full
        assert "积极" not in full, "旧成长内容应被替换"


# ============================================================
# 4. load() 保持不变 — 返回完整内容
# ============================================================

def test_load_returns_full_content():
    """load() 应返回完整内容（固定 + 成长），行为不变。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        content = (
            "# Soul — 固定部分\n"
            "我是助手。\n"
            "\n"
            "# Soul — 成长部分\n"
            "## 性格倾向\n"
            "简洁\n"
        )
        sm.save(content)
        assert sm.load() == content


def test_load_returns_full_content_old_format():
    """load() 对旧格式文件应原样返回。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        content = "旧格式内容\n"
        sm.save(content)
        assert sm.load() == content


# ============================================================
# 5. 分隔标记一致性
# ============================================================

def test_growth_header_is_separator():
    """# Soul — 成长部分 应作为固定和成长的分隔标记。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save(
            "# Soul — 固定部分\n"
            "固定内容\n"
            "\n"
            "# Soul — 成长部分\n"
            "成长内容\n"
        )
        fixed = sm.load_fixed()
        growth = sm.load_growth()
        assert fixed.strip().endswith("固定内容"), \
            f"固定部分应以 '固定内容' 结尾，实际: {fixed!r}"
        assert growth.strip().startswith("##") or "成长内容" in growth, \
            f"成长部分应包含成长内容，实际: {growth!r}"


def test_save_growth_creates_separator_on_append():
    """save_growth 追加时应创建分隔标记。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save("# Soul — 固定部分\n固定内容\n")
        sm.save_growth("# Soul — 成长部分\n成长内容\n")
        full = sm.load()
        assert "# Soul — 成长部分" in full
        # 分隔标记之后是成长内容
        idx = full.index("# Soul — 成长部分")
        assert "成长内容" in full[idx:]
