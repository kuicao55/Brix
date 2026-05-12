"""补全器从 CommandRegistry 读取的测试。"""
from __future__ import annotations

from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document

from capability.command.base import (
    Command,
    CommandContext,
    CommandMeta,
    CommandResult,
    CommandResultType,
    CommandType,
)
from capability.command.registry import CommandRegistry
from cli.completer import SlashCommandCompleter


class _CmdA(Command):
    @property
    def meta(self):
        return CommandMeta(name="alpha", description="Alpha cmd", type=CommandType.SYSTEM)

    async def execute(self, args, context):
        return CommandResult(type=CommandResultType.NONE)


class _CmdB(Command):
    @property
    def meta(self):
        return CommandMeta(name="beta", description="Beta cmd", type=CommandType.SKILL)

    async def execute(self, args, context):
        return CommandResult(type=CommandResultType.PROMPT, prompt_text="p")


def _make_completer() -> tuple[SlashCommandCompleter, CommandRegistry]:
    reg = CommandRegistry()
    reg.register(_CmdA())
    reg.register(_CmdB())
    completer = SlashCommandCompleter(reg)
    return completer, reg


def _get_completions(completer: SlashCommandCompleter, text: str) -> list[Completion]:
    doc = Document(text=text, cursor_position=len(text))
    return list(completer.get_completions(doc, None))


def test_completer_from_registry():
    """补全器应从 CommandRegistry 读取命令。"""
    completer, _ = _make_completer()
    completions = _get_completions(completer, "/")
    names = [c.text for c in completions]
    assert "/alpha" in names
    assert "/beta" in names


def test_completer_prefix_filter():
    """前缀过滤应正常工作。"""
    completer, _ = _make_completer()
    completions = _get_completions(completer, "/al")
    names = [c.text for c in completions]
    assert names == ["/alpha"]


def test_completer_no_slash():
    """非 / 开头应无补全。"""
    completer, _ = _make_completer()
    completions = _get_completions(completer, "hello")
    assert completions == []


def test_completer_with_space():
    """有空格时不应补全。"""
    completer, _ = _make_completer()
    completions = _get_completions(completer, "/alpha args")
    assert completions == []
