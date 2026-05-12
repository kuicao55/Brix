"""CommandRegistry 测试。"""
from __future__ import annotations

import pytest
from capability.command.base import (
    Command,
    CommandContext,
    CommandMeta,
    CommandResult,
    CommandResultType,
    CommandType,
)
from capability.command.registry import CommandRegistry


class _SystemCmd(Command):
    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(name="test-sys", description="test system", type=CommandType.SYSTEM)

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        return CommandResult(type=CommandResultType.NONE)


class _SkillCmd(Command):
    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="test-skill",
            description="test skill",
            type=CommandType.SKILL,
            when_to_use="当用户要求测试时",
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        return CommandResult(type=CommandResultType.PROMPT, prompt_text="do test")


class _HiddenCmd(Command):
    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="hidden",
            description="hidden cmd",
            type=CommandType.SYSTEM,
            user_invocable=False,
            disable_model_invocation=True,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        return CommandResult(type=CommandResultType.NONE)


def test_register_and_get():
    """注册后应能按名称查找。"""
    reg = CommandRegistry()
    cmd = _SystemCmd()
    reg.register(cmd)
    assert reg.get("test-sys") is cmd


def test_get_unknown_returns_none():
    """查找未注册的命令应返回 None。"""
    reg = CommandRegistry()
    assert reg.get("nonexistent") is None


def test_list_all():
    """list_all 应返回所有命令的元数据。"""
    reg = CommandRegistry()
    reg.register(_SystemCmd())
    reg.register(_SkillCmd())
    metas = reg.list_all()
    assert len(metas) == 2
    names = {m.name for m in metas}
    assert names == {"test-sys", "test-skill"}


def test_list_all_excludes_hidden():
    """list_all 默认应排除隐藏命令。"""
    reg = CommandRegistry()
    reg.register(_SystemCmd())
    reg.register(_HiddenCmd())
    metas = reg.list_all()
    assert len(metas) == 1
    assert metas[0].name == "test-sys"


def test_list_all_include_hidden():
    """list_all(include_hidden=True) 应包含隐藏命令。"""
    reg = CommandRegistry()
    reg.register(_SystemCmd())
    reg.register(_HiddenCmd())
    metas = reg.list_all(include_hidden=True)
    assert len(metas) == 2


def test_get_skill_listing_text_empty():
    """无 Skill 时应返回空字符串。"""
    reg = CommandRegistry()
    reg.register(_SystemCmd())
    assert reg.get_skill_listing_text() == ""


def test_get_skill_listing_text():
    """应只列出 Skill 类型命令。"""
    reg = CommandRegistry()
    reg.register(_SystemCmd())
    reg.register(_SkillCmd())
    text = reg.get_skill_listing_text()
    assert "test-skill" in text
    assert "test-sys" not in text
    assert "当用户要求测试时" in text


def test_overwrite_on_duplicate_register():
    """重复注册同名命令应覆盖。"""
    reg = CommandRegistry()
    reg.register(_SystemCmd())
    reg.register(_SystemCmd())  # 重复
    assert reg.get("test-sys") is not None
    metas = reg.list_all()
    assert len(metas) == 1
