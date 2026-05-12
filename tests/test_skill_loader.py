"""SKILL.md 加载器测试。"""
from __future__ import annotations

import pytest
from pathlib import Path

from capability.command.loader import FileSkill


def _write_skill(tmp_path: Path, name: str, content: str) -> Path:
    """辅助函数：写入 SKILL.md 并返回目录路径。"""
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


def test_parse_frontmatter(tmp_path):
    """应正确解析 YAML frontmatter。"""
    content = """---
name: commit
description: 提交代码变更
whenToUse: 当用户要求提交代码时
allowedTools:
  - Bash
  - Read
model: haiku
---

# Commit Skill

请按以下步骤提交代码。
"""
    skill_dir = _write_skill(tmp_path, "commit", content)
    skill = FileSkill(skill_dir)

    assert skill.meta.name == "commit"
    assert skill.meta.description == "提交代码变更"
    assert skill.meta.when_to_use == "当用户要求提交代码时"
    assert skill.meta.allowed_tools == ["Bash", "Read"]
    assert skill.meta.model == "haiku"
    assert skill.meta.skill_root == str(skill_dir)


def test_parse_no_frontmatter(tmp_path):
    """无 frontmatter 时应使用目录名作为 name。"""
    content = """# Simple Skill

Just a prompt.
"""
    skill_dir = _write_skill(tmp_path, "simple", content)
    skill = FileSkill(skill_dir)

    assert skill.meta.name == "simple"
    assert skill.meta.description == ""


@pytest.mark.asyncio
async def test_variable_substitution_arguments(tmp_path):
    """$ARGUMENTS 应被替换为传入的参数。"""
    content = """---
name: test
description: test
---

Run with: $ARGUMENTS
"""
    skill_dir = _write_skill(tmp_path, "test", content)
    skill = FileSkill(skill_dir)

    prompt = await skill.get_prompt("-m 'fix bug'", {})
    assert "-m 'fix bug'" in prompt
    assert "$ARGUMENTS" not in prompt


@pytest.mark.asyncio
async def test_variable_substitution_positional(tmp_path):
    """$0, $1 应被替换为位置参数。"""
    content = """---
name: test
description: test
---

First: $0
Second: $1
"""
    skill_dir = _write_skill(tmp_path, "test", content)
    skill = FileSkill(skill_dir)

    prompt = await skill.get_prompt("hello world", {})
    assert "First: hello" in prompt
    assert "Second: world" in prompt


@pytest.mark.asyncio
async def test_variable_substitution_skill_dir(tmp_path):
    """${SKILL_DIR} 应被替换为 Skill 目录路径。"""
    content = """---
name: test
description: test
---

Dir: ${SKILL_DIR}
"""
    skill_dir = _write_skill(tmp_path, "test", content)
    skill = FileSkill(skill_dir)

    prompt = await skill.get_prompt("", {})
    assert str(skill_dir) in prompt
    assert "${SKILL_DIR}" not in prompt


@pytest.mark.asyncio
async def test_variable_substitution_session_id(tmp_path):
    """${SESSION_ID} 应被替换为会话 ID。"""
    content = """---
name: test
description: test
---

Session: ${SESSION_ID}
"""
    skill_dir = _write_skill(tmp_path, "test", content)
    skill = FileSkill(skill_dir)

    prompt = await skill.get_prompt("", {"session_id": "abc-123"})
    assert "abc-123" in prompt


@pytest.mark.asyncio
async def test_auto_append_arguments(tmp_path):
    """prompt 中无 $ARGUMENTS 时应自动追加。"""
    content = """---
name: test
description: test
---

Do something.
"""
    skill_dir = _write_skill(tmp_path, "test", content)
    skill = FileSkill(skill_dir)

    prompt = await skill.get_prompt("my args", {})
    assert "my args" in prompt


def test_parse_defaults(tmp_path):
    """默认值应正确设置。"""
    content = """---
name: test
description: test
---
Prompt.
"""
    skill_dir = _write_skill(tmp_path, "test", content)
    skill = FileSkill(skill_dir)

    assert skill.meta.context == "inline"
    assert skill.meta.user_invocable is True
    assert skill.meta.disable_model_invocation is False
    assert skill.meta.allowed_tools == []


def test_parse_user_invocable_false(tmp_path):
    """userInvocable: false 应正确解析。"""
    content = """---
name: hidden-skill
description: hidden
userInvocable: false
disableModelInvocation: true
---
Prompt.
"""
    skill_dir = _write_skill(tmp_path, "hidden-skill", content)
    skill = FileSkill(skill_dir)

    assert skill.meta.user_invocable is False
    assert skill.meta.disable_model_invocation is True
