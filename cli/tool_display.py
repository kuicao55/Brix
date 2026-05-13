"""Tool execution status display panels."""

from __future__ import annotations

import json

from rich.console import Console
from rich.markup import escape as markup_escape
from rich.panel import Panel
from rich.text import Text

from cli.spinner import Spinner


class ToolDisplay:
    """Formatted panels for tool call start and result display."""

    TOOL_ICONS = {
        "bash": "\u26a1",
        "file_read": "\U0001f4c4",
        "file_write": "\u270f\ufe0f",
        "file_edit": "\U0001f4dd",
        "web_search": "\U0001f50e",
        "calculator": "\U0001f9ee",
        "weather": "\U0001f324\ufe0f",
    }

    def __init__(self, console: Console) -> None:
        self.console = console
        self._active_spinner: Spinner | None = None

    def show_tool_start(self, tool_name: str, tool_input: dict) -> None:
        """Display a formatted panel when a tool call begins."""
        safe_name = markup_escape(str(tool_name))
        icon = self.TOOL_ICONS.get(tool_name, "\U0001f527")
        detail = self._format_detail(tool_name, tool_input)
        # Loading indicator: ⏺ Calling tools... — shows tool is running
        loading = Text()
        loading.append("⏺ ", style="dim")
        loading.append("Calling tools...", style="dim")
        self.console.print(loading)
        panel = Panel(
            detail,
            title="[tool.name]{} {}[/]".format(icon, safe_name),
            title_align="left",
            border_style="tool.border",
            padding=(0, 1),
        )
        self.console.print(panel)

    def show_tool_result(
        self,
        tool_name: str,
        result: str,
        elapsed_ms: float,
        is_error: bool = False,
    ) -> None:
        """Display a one-line summary when a tool call completes."""
        # 停止之前的 thinking spinner（如果有）
        self.stop_thinking()
        safe_name = markup_escape(str(tool_name))
        icon = self.TOOL_ICONS.get(tool_name, "\U0001f527")
        status_style = "red" if is_error else "green"
        status_icon = "\u2717" if is_error else "\u2713"
        elapsed_str = "{:.0f}ms".format(elapsed_ms)

        preview = result[:200].replace("\n", " ")
        if len(result) > 200:
            preview += "\u2026"

        text = Text()
        text.append("\u23bf ", style="dim")
        text.append("{} ".format(icon), style="dim")
        text.append(safe_name, style="tool.name")
        text.append("  {}".format(status_icon), style=status_style)
        text.append("  {}".format(elapsed_str), style="dim cyan")
        if is_error:
            text.append("  {}".format(preview), style="red")
        self.console.print(text)
        # 工具执行完毕，启动 thinking spinner 等待 LLM 响应
        self.start_thinking()

    def start_thinking(self) -> None:
        """启动 thinking spinner，在 LLM 思考期间显示动画。"""
        if self._active_spinner is None:
            self._active_spinner = Spinner(self.console, label="Thinking...")
            self._active_spinner.start()

    def stop_thinking(self) -> None:
        """停止 thinking spinner。"""
        if self._active_spinner is not None:
            self._active_spinner.stop()
            self._active_spinner = None

    def _format_detail(self, tool_name: str, tool_input: dict) -> str:
        """Return tool-specific detail string for the panel body."""
        if not isinstance(tool_input, dict):
            try:
                preview = json.dumps(tool_input, ensure_ascii=False)[:150]
            except (TypeError, ValueError):
                preview = repr(tool_input)[:150]
            return markup_escape(preview)

        if tool_name == "bash":
            cmd = markup_escape(str(tool_input.get("command", "")))
            return "$ {}".format(cmd)
        elif tool_name == "file_read":
            path = markup_escape(str(tool_input.get("path", "")))
            return "\U0001f4c4 Reading {}".format(path)
        elif tool_name == "file_write":
            path = markup_escape(str(tool_input.get("path", "")))
            content = str(tool_input.get("content", ""))
            lines = content.count("\n") + 1
            return "\u270f\ufe0f Writing {} ({} lines)".format(path, lines)
        elif tool_name == "file_edit":
            path = markup_escape(str(tool_input.get("path", "")))
            return "\U0001f4dd Editing {}".format(path)
        elif tool_name == "web_search":
            query = markup_escape(str(tool_input.get("query", "")))
            return "\U0001f50e Searching: {}".format(query)
        else:
            try:
                preview = json.dumps(tool_input, ensure_ascii=False)[:150]
            except (TypeError, ValueError):
                preview = repr(tool_input)[:150]
            return markup_escape(preview)

    def cleanup(self) -> None:
        """安全清理：异常路径调用，确保 spinner 不泄漏"""
        self.stop_thinking()
