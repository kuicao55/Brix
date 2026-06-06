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


# ============================================================
# 6. 行锚定解析 — 防止正文中的标题文本被误匹配
# ============================================================

def test_load_fixed_header_in_body_not_matched():
    """固定部分正文中出现 '# Soul — 成长部分' 时不应被误识别为分隔标记。

    这是 CQR Finding 2 的核心回归测试：content.find() 子串匹配会错误地
    把正文里的标题文本当作真正的 section header。
    """
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        # 固定部分正文里提到了成长部分标题（比如引用说明）
        sm.save(
            "# Soul — 固定部分\n"
            "注意：不要修改 # Soul — 成长部分 的格式。\n"
            "保持专业。\n"
        )
        fixed = sm.load_fixed()
        # 应该返回全部内容（因为没有真正的成长部分 header 行）
        assert "注意：不要修改" in fixed
        assert "保持专业" in fixed


def test_load_growth_header_in_body_not_matched():
    """固定部分正文中出现 '# Soul — 成长部分' 时，load_growth 不应误匹配。

    验证 load_growth 使用行锚定解析而非子串搜索。
    """
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        # 固定部分正文里嵌入了成长标题文本（但不在独立行上）
        sm.save(
            "# Soul — 固定部分\n"
            "提示：请参考 # Soul — 成长部分 的格式。\n"
            "保持简洁。\n"
        )
        growth = sm.load_growth()
        # 没有真正的成长部分 header 行，load_growth 应返回空
        assert growth == "", \
            f"正文中的标题文本不应被误匹配为 section header: {growth!r}"


def test_save_growth_header_in_fixed_body_preserved():
    """save_growth 替换成长部分时，固定部分正文中的标题文本应被保留。

    验证行锚定解析在写入路径也正确工作。
    """
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save(
            "# Soul — 固定部分\n"
            "记住 # Soul — 成长部分 的格式很重要。\n"
            "\n"
            "# Soul — 成长部分\n"
            "旧内容\n"
        )
        sm.save_growth(
            "# Soul — 成长部分\n"
            "新内容\n"
        )
        full = sm.load()
        # 固定部分正文中的引用应被保留
        assert "记住 # Soul — 成长部分 的格式很重要" in full
        # 新成长内容应存在
        assert "新内容" in full
        # 旧成长内容应被替换
        assert "旧内容" not in full


# ============================================================
# 7. save_growth — growth_content 缺少 header 时自动补齐
# ============================================================

def test_save_growth_auto_prepends_header_if_missing():
    """save_growth 的 growth_content 如果缺少成长标题，应自动补齐。

    这是 CQR Finding 3 的核心测试：防止后续 load_growth() 返回空。
    """
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save("# Soul — 固定部分\n我是助手。\n")
        # 调用时不带成长标题
        sm.save_growth("## 性格倾向\n简洁直接\n")
        growth = sm.load_growth()
        assert "性格倾向" in growth, \
            f"缺少 header 时应自动补齐，load_growth() 不应返回空: {growth!r}"
        assert "简洁直接" in growth


def test_save_growth_auto_prepends_header_on_update():
    """save_growth 更新已有成长部分时，如果新内容缺少 header，也应自动补齐。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save(
            "# Soul — 固定部分\n"
            "我是助手。\n"
            "\n"
            "# Soul — 成长部分\n"
            "旧成长内容\n"
        )
        # 新内容不带成长标题
        sm.save_growth("## 新经验\n学到新东西\n")
        growth = sm.load_growth()
        assert "新经验" in growth
        assert "学到新东西" in growth
        assert "旧成长内容" not in growth


# ============================================================
# 8. CQR Finding 2: save_growth 不应在 read 失败后覆盖文件
# ============================================================

def test_save_growth_aborts_on_read_failure():
    """save_growth 中若 load() 因 OSError 返回空字符串，不应覆盖已有文件内容。

    回归测试：tolerant load() 在文件存在但读取失败时返回 ""，
    save_growth 应使用 strict read，读取失败时 abort 并 re-raise。
    """
    from memory.soul import SoulManager
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        original = (
            "# Soul — 固定部分\n"
            "我是用户的助手。\n"
            "\n"
            "# Soul — 成长部分\n"
            "## 情绪基线\n"
            "平静\n"
        )
        sm.save(original)

        # 模拟 read_text 抛出 OSError（瞬时读取失败）
        original_read_text = Path.read_text

        def failing_read_text(self_path, *args, **kwargs):
            if str(self_path).endswith("soul.md") and "lock" not in str(self_path):
                raise OSError("瞬时读取失败")
            return original_read_text(self_path, *args, **kwargs)

        with patch.object(Path, "read_text", failing_read_text):
            with pytest.raises(OSError, match="瞬时读取失败"):
                sm.save_growth("# Soul — 成长部分\n## 情绪基线\n积极\n")

        # 文件内容应保持不变（未被覆盖）
        content = sm.load()
        assert "平静" in content, f"文件不应被覆盖: {content!r}"
        assert "我是用户的助手" in content, f"固定部分应保留: {content!r}"


# ============================================================
# 9. CQR Finding 3: CRLF 行尾不应破坏 header 匹配
# ============================================================

def test_find_header_line_with_crlf():
    """_find_header_line 应正确处理 CRLF 行尾的文件。

    回归测试：CRLF 文件 split 后行尾保留 \\r，导致 header 匹配失败。
    """
    from memory.soul import _find_header_line, _GROWTH_HEADER
    # 模拟 CRLF 文件 splitlines 保留 \r 的情况
    lines = [
        "# Soul — 固定部分\r",
        "我是助手。\r",
        "\r",
        "# Soul — 成长部分\r",
        "## 性格倾向\r",
        "简洁\r",
    ]
    idx = _find_header_line(lines, _GROWTH_HEADER)
    assert idx == 3, f"CRLF 行尾应匹配成长标题，实际索引: {idx}"


def test_load_fixed_crlf_file():
    """load_fixed 应正确处理 CRLF 行尾的 soul.md。

    使用 newline='' 写入以保留 \\r\\n，验证 load_fixed 能正确解析。
    """
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm._path.parent.mkdir(parents=True, exist_ok=True)
        crlf_content = (
            "# Soul — 固定部分\r\n"
            "我是助手。\r\n"
            "\r\n"
            "# Soul — 成长部分\r\n"
            "## 性格倾向\r\n"
            "简洁\r\n"
        )
        # newline='' 禁止换行翻译，保留文件中的 \r\n
        with open(str(sm._path), "w", encoding="utf-8", newline="") as f:
            f.write(crlf_content)

        fixed = sm.load_fixed()
        assert "我是助手" in fixed, f"CRLF 文件应正确解析固定部分: {fixed!r}"
        assert "性格倾向" not in fixed, f"成长部分不应出现在固定部分: {fixed!r}"


def test_load_growth_crlf_file():
    """load_growth 应正确处理 CRLF 行尾的 soul.md。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm._path.parent.mkdir(parents=True, exist_ok=True)
        crlf_content = (
            "# Soul — 固定部分\r\n"
            "我是助手。\r\n"
            "\r\n"
            "# Soul — 成长部分\r\n"
            "## 性格倾向\r\n"
            "简洁\r\n"
        )
        with open(str(sm._path), "w", encoding="utf-8", newline="") as f:
            f.write(crlf_content)

        growth = sm.load_growth()
        assert "性格倾向" in growth, f"CRLF 文件应正确解析成长部分: {growth!r}"
        assert "简洁" in growth
        assert "我是助手" not in growth


# ============================================================
# 10. CQR: save_growth 空内容不应破坏已有成长
# ============================================================

def test_save_growth_empty_string_preserves_existing_growth():
    """save_growth("") 不应破坏已有的成长部分。

    回归测试：空字符串经过 _ensure_growth_header() 后变成纯 header，
    导致所有已有成长内容丢失。
    """
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save(
            "# Soul — 固定部分\n"
            "我是助手。\n"
            "\n"
            "# Soul — 成长部分\n"
            "## 性格倾向\n"
            "简洁直接\n"
            "\n"
            "## 经验教训\n"
            "用户不喜欢冗长\n"
        )
        # 调用空内容
        sm.save_growth("")
        growth = sm.load_growth()
        assert "性格倾向" in growth, \
            f"空内容不应破坏已有成长，但成长部分被清空: {growth!r}"
        assert "简洁直接" in growth, \
            f"已有成长内容应保留: {growth!r}"
        assert "经验教训" in growth, \
            f"已有成长内容应保留: {growth!r}"


def test_save_growth_whitespace_preserves_existing_growth():
    """save_growth("   ") 不应破坏已有的成长部分。"""
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save(
            "# Soul — 固定部分\n"
            "我是助手。\n"
            "\n"
            "# Soul — 成长部分\n"
            "## 情绪基线\n"
            "平静\n"
        )
        # 调用纯空白内容
        sm.save_growth("   \n  \n")
        growth = sm.load_growth()
        assert "情绪基线" in growth, \
            f"纯空白内容不应破坏已有成长: {growth!r}"
        assert "平静" in growth, \
            f"已有成长内容应保留: {growth!r}"


def test_save_growth_leading_newline_header_preserves_existing_growth():
    """save_growth("\\n# Soul — 成长部分\\n") 不应破坏已有的成长部分。

    回归测试：leading newline 导致 _ensure_growth_header 返回未规范化内容，
    空 body guard 的 slice 偏移不对，误判为非空从而替换已有成长。
    """
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save(
            "# Soul — 固定部分\n"
            "我是助手。\n"
            "\n"
            "# Soul — 成长部分\n"
            "## 性格倾向\n"
            "简洁直接\n"
            "\n"
            "## 经验教训\n"
            "用户不喜欢冗长\n"
        )
        # 调用带有 leading newline 的 header-only 内容
        sm.save_growth("\n# Soul — 成长部分\n")
        growth = sm.load_growth()
        assert "性格倾向" in growth, \
            f"leading newline header-only 不应破坏已有成长，但成长部分被清空: {growth!r}"
        assert "简洁直接" in growth, \
            f"已有成长内容应保留: {growth!r}"
        assert "经验教训" in growth, \
            f"已有成长内容应保留: {growth!r}"


def test_save_growth_empty_on_no_existing_growth():
    """没有已有成长时，save_growth("") 也不应写入纯 header 的空成长。

    无已有成长 + 空内容 = 应该是 no-op（无文件变更或只保留固定部分）。
    """
    from memory.soul import SoulManager
    with tempfile.TemporaryDirectory() as d:
        sm = SoulManager(Path(d))
        sm.save("# Soul — 固定部分\n我是助手。\n")
        sm.save_growth("")
        full = sm.load()
        assert "我是助手" in full, "固定部分应保留"
        # 不应出现没有实质内容的纯成长 header
        growth = sm.load_growth()
        assert growth.strip() == "", \
            f"空内容不应创建纯 header 的成长部分: {growth!r}"
