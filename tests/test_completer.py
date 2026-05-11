"""Tests for SlashCommandCompleter."""
from __future__ import annotations

from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document

from cli.completer import SlashCommandCompleter


def _get_completions(text: str) -> list[Completion]:
    """Helper: get completions for given input text."""
    completer = SlashCommandCompleter()
    doc = Document(text=text, cursor_position=len(text))
    return list(completer.get_completions(doc, None))


def test_slash_shows_all_commands():
    """输入 / 应显示所有命令。"""
    completions = _get_completions("/")
    names = [c.text for c in completions]
    assert "/help" in names
    assert "/quit" in names
    assert "/clear" in names
    assert "/resume" in names
    assert len(completions) >= 7


def test_prefix_filter():
    """输入 /he 应只匹配 /help。"""
    completions = _get_completions("/he")
    names = [c.text for c in completions]
    assert names == ["/help"]


def test_prefix_filter_multiple():
    """输入 /re 应匹配 /resume。"""
    completions = _get_completions("/re")
    names = [c.text for c in completions]
    assert "/resume" in names


def test_no_match():
    """输入 /zzz 应无匹配。"""
    completions = _get_completions("/zzz")
    assert completions == []


def test_no_slash_no_completion():
    """不以 / 开头时不应有补全。"""
    completions = _get_completions("hello")
    assert completions == []


def test_space_no_completion():
    """输入包含空格（命令参数）时不应补全。"""
    completions = _get_completions("/resume abc")
    assert completions == []


def test_start_position_replaces_input():
    """补全应替换整个输入（从行首开始）。"""
    completions = _get_completions("/he")
    # start_position 为负数，表示从光标位置向前替换
    assert all(c.start_position < 0 for c in completions)
    # 所有补全项的替换范围应一致
    positions = {c.start_position for c in completions}
    assert len(positions) == 1


def test_display_meta_shows_description():
    """补全项应包含描述作为 display_meta。"""
    completions = _get_completions("/help")
    help_completion = next(c for c in completions if c.text == "/help")
    assert help_completion.display_meta is not None
    # display_meta 是 FormattedText，转为字符串检查
    meta_str = str(help_completion.display_meta)
    assert "显示" in meta_str


def test_case_insensitive():
    """大小写不敏感匹配。"""
    completions = _get_completions("/HELP")
    names = [c.text for c in completions]
    assert "/help" in names
