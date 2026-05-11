"""斜杠命令自动补全器 — 基于 prompt_toolkit Completer 协议。"""

from __future__ import annotations

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from capability.basics.commands import COMMANDS


class SlashCommandCompleter(Completer):
    """输入 / 时自动弹出命令列表，支持前缀过滤。

    仅当光标位于行首且输入以 / 开头时激活。
    """

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
        for cmd, description in COMMANDS:
            # 过滤掉带 [id] 等参数占位符的命令名用于匹配
            cmd_name = cmd.split()[0]  # "/resume [id]" -> "/resume"
            if cmd_name.lower().startswith(lower_word):
                # 补全文本：用完整命令名替换当前输入
                completions.append(
                    Completion(
                        text=cmd_name,
                        start_position=-len(word),
                        display_meta=description,
                    )
                )

        return completions
