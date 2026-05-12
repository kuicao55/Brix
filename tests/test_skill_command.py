"""SkillCommand 测试。"""
from __future__ import annotations

import pytest
from pathlib import Path

from capability.command.base import CommandContext, CommandResultType, CommandType
from capability.command.skill import SkillCommand


def _write_skill(tmp_path: Path, name: str, content: str) -> Path:
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


def test_meta_from_skill(tmp_path):
    """SkillCommand 的 meta 应来自 FileSkill。"""
    content = """\
---
name: commit
description: 提交代码
whenToUse: 当用户要求提交时
allowedTools:
  - Bash
model: haiku
---
Do commit.
"""
    skill_dir = _write_skill(tmp_path, "commit", content)
    cmd = SkillCommand(skill_dir)

    assert cmd.meta.name == "commit"
    assert cmd.meta.description == "提交代码"
    assert cmd.meta.type == CommandType.SKILL
    assert cmd.meta.when_to_use == "当用户要求提交时"


@pytest.mark.asyncio
async def test_execute_returns_prompt(tmp_path):
    """execute 应返回 PROMPT 类型结果。"""
    content = """\
---
name: test
description: test
---
Run: $ARGUMENTS
"""
    skill_dir = _write_skill(tmp_path, "test", content)
    cmd = SkillCommand(skill_dir)

    result = await cmd.execute("-m 'fix'", CommandContext())
    assert result.type == CommandResultType.PROMPT
    assert "fix" in result.prompt_text


@pytest.mark.asyncio
async def test_execute_with_allowed_tools(tmp_path):
    """allowedTools 应传递到 CommandResult。"""
    content = """\
---
name: test
description: test
allowedTools:
  - Bash
  - Read
---
Do something.
"""
    skill_dir = _write_skill(tmp_path, "test", content)
    cmd = SkillCommand(skill_dir)

    result = await cmd.execute("", CommandContext())
    assert result.allowed_tools == ["Bash", "Read"]


@pytest.mark.asyncio
async def test_execute_with_model_override(tmp_path):
    """model 应传递到 CommandResult。"""
    content = """\
---
name: test
description: test
model: haiku
---
Do something.
"""
    skill_dir = _write_skill(tmp_path, "test", content)
    cmd = SkillCommand(skill_dir)

    result = await cmd.execute("", CommandContext())
    assert result.model == "haiku"


@pytest.mark.asyncio
async def test_execute_no_overrides(tmp_path):
    """无 allowedTools/model 时应返回 None。"""
    content = """\
---
name: test
description: test
---
Do something.
"""
    skill_dir = _write_skill(tmp_path, "test", content)
    cmd = SkillCommand(skill_dir)

    result = await cmd.execute("", CommandContext())
    assert result.allowed_tools is None
    assert result.model is None
