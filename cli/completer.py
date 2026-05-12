"""斜杠命令自动补全器 -- 基于 prompt_toolkit Completer 协议。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from capability.basics.commands import COMMANDS

if TYPE_CHECKING:
    from capability.command.registry import CommandRegistry


class SlashCommandCompleter(Completer):
    """输入 / 时自动弹出命令列表，支持前缀过滤。

    仅当光标位于行首且输入以 / 开头时激活。

    Args:
        registry: 可选的 CommandRegistry，若提供则从注册表读取命令列表；
                  否则回退到旧的 COMMANDS 静态列表。
    """

    def __init__(self, registry: CommandRegistry | None = None) -> None:
        self._registry = registry

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> list[Completion]:
        text = document.text_before_cursor

        # 仅在行首输入 / 开头时触发
        if not text.startswith("/"):
            return []

        # 已有空格说明在输入参数，不补全
        if " " in text:
            return []

        word = text  # 包含 / 的完整输入
        lower_word = word.lower()

        completions: list[Completion] = []

        if self._registry is not None:
            # 从 CommandRegistry 读取命令列表
            for meta in self._registry.list_all():
                cmd_name = f"/{meta.name}"
                if cmd_name.lower().startswith(lower_word):
                    completions.append(
                        Completion(
                            text=cmd_name,
                            start_position=-len(word),
                            display_meta=meta.description,
                        )
                    )
        else:
            # 回退到旧的 COMMANDS 静态列表
            for cmd, description in COMMANDS:
                cmd_name = cmd.split()[0]  # "/resume [id]" -> "/resume"
                if cmd_name.lower().startswith(lower_word):
                    completions.append(
                        Completion(
                            text=cmd_name,
                            start_position=-len(word),
                            display_meta=description,
                        )
                    )

        return completions
