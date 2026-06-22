"""TuiAdapter — 基于 prompt_toolkit + Rich 的终端 UI 实现。

实现 UIAdapter Protocol，将所有 TUI 渲染逻辑封装在此。
从 cli/app.py 的 _process_streaming() 中搬出的渲染逻辑。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from prompt_toolkit import HTML, PromptSession
from prompt_toolkit.completion import FuzzyCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.text import Text

from cli.banner import show_banner
from cli.completer import SlashCommandCompleter
from cli.display import render_history as _render_history
from cli.paginated_selector import PaginatedSelector
from cli.spinner import Spinner
from cli.stage_indicator import StageIndicator
from cli.status_bar import StatusBarRenderer
from cli.stream_renderer import StreamRenderer
from cli.thinking_renderer import ThinkingRenderer
from cli.tool_display import ToolDisplay
from cli.voice_display import VoiceDisplay

# 语义化样式 → Rich 样式映射
_STYLE_MAP = {
    "success": "green",
    "error": "red",
    "muted": "dim",
    "accent": "bold cyan",
    "warning": "yellow",
}


def _rich_style(semantic: str) -> str:
    """将语义化样式标签映射为 Rich 样式字符串。"""
    return _STYLE_MAP.get(semantic, semantic)


class TuiAdapter:
    """基于 prompt_toolkit + Rich 的终端 UI 实现。

    封装所有 TUI 渲染逻辑，实现 UIAdapter Protocol。
    """

    def __init__(
        self,
        console: Console,
        config: dict,
        command_registry: Any = None,
        status_bar_renderer: StatusBarRenderer | None = None,
    ) -> None:
        self._console = console
        self._config = config
        self._command_registry = command_registry
        self._status_bar_renderer = status_bar_renderer
        self._status_bar_enabled = status_bar_renderer is not None

        # Streaming 渲染器（延迟创建）
        self._stream_renderer: StreamRenderer | None = None
        self._thinking_renderer: ThinkingRenderer | None = None

        # Tool 展示
        self._tool_display: ToolDisplay | None = None

        # 阶段指示器
        self._stage_indicator: StageIndicator | None = None

        # Voice 展示
        self._voice_display: VoiceDisplay | None = None

        # prompt_toolkit session（延迟创建）
        self._session: PromptSession | None = None

    # ------------------------------------------------------------------
    # 一次性输出
    # ------------------------------------------------------------------

    def print(self, text: str, style: str = "") -> None:
        """打印一行文本（语义化样式标签）。"""
        rich_style = _rich_style(style) if style else ""
        if rich_style:
            self._console.print(f"[{rich_style}]{text}[/]")
        else:
            self._console.print(text)

    def print_markdown(self, markdown: str) -> None:
        """渲染并打印 markdown 内容。"""
        from rich.markdown import Markdown as RichMarkdown
        self._console.print(RichMarkdown(markdown))

    # ------------------------------------------------------------------
    # Streaming 渲染
    # ------------------------------------------------------------------

    def start_thinking(self) -> None:
        """开始 thinking/reasoning 内容块。"""
        if self._tool_display:
            self._tool_display.stop_thinking()
        self.stop_stage()
        self._thinking_renderer = ThinkingRenderer(self._console)
        self._thinking_renderer.start()

    def push_thinking_delta(self, text: str) -> None:
        """推送 thinking 文本增量。"""
        if self._thinking_renderer is None:
            self.start_thinking()
        self._thinking_renderer.push_delta(text)

    def flush_thinking(self) -> None:
        """结束 thinking 内容块。"""
        if self._thinking_renderer is not None:
            self._thinking_renderer.flush()
            self._thinking_renderer = None

    def start_streaming(self) -> None:
        """开始正式回复的流式渲染。"""
        if self._tool_display:
            self._tool_display.stop_thinking()
        self.stop_stage()
        marker = Text("⏺ ", style="green")
        self._stream_renderer = StreamRenderer(self._console, marker=marker)
        self._stream_renderer.start()

    def push_text_delta(self, text: str) -> None:
        """推送回复文本增量。"""
        if self._stream_renderer is None:
            self.start_streaming()
        self._stream_renderer.push_delta(text)

    def flush_streaming(self) -> None:
        """结束流式渲染，确保所有内容输出完毕。"""
        if self._stream_renderer is not None:
            self._stream_renderer.flush()
            self._stream_renderer = None

    # ------------------------------------------------------------------
    # Tool 展示
    # ------------------------------------------------------------------

    def show_tool_start(self, name: str, input_data: dict) -> None:
        """展示工具调用开始。"""
        self._ensure_tool_display()
        self._console.print()  # 工具调用前的间隔
        self._tool_display.show_tool_start(name, input_data)

    def show_tool_result(
        self, name: str, result: str, ms: int, is_error: bool = False
    ) -> None:
        """展示工具调用结果。"""
        self._ensure_tool_display()
        self._tool_display.show_tool_result(name, result, ms, is_error=is_error)
        self._console.print()  # 工具结果后的间隔

    def _ensure_tool_display(self) -> None:
        """延迟创建 ToolDisplay。"""
        if self._tool_display is None:
            self._tool_display = ToolDisplay(self._console)

    # ------------------------------------------------------------------
    # 状态指示
    # ------------------------------------------------------------------

    def update_stage(self, stage: str, detail: str = "") -> None:
        """更新当前处理阶段指示器。"""
        if self._stage_indicator is None:
            self._stage_indicator = StageIndicator(self._console)
        self._stage_indicator.update(stage, detail)

    def stop_stage(self) -> None:
        """停止阶段指示器。"""
        if self._stage_indicator is not None:
            self._stage_indicator.stop_silent()
            self._stage_indicator = None

    # ------------------------------------------------------------------
    # 交互式输入
    # ------------------------------------------------------------------

    async def prompt_async(self, prefix: str = "") -> str:
        """异步等待用户输入。"""
        self._ensure_session()
        # 转换语义化 prefix 为 prompt_toolkit HTML
        html_prefix = HTML(f'<ansicyan><b>{prefix}</b></ansicyan>')
        return await self._session.prompt_async(html_prefix)

    async def select_paginated(
        self,
        items: list,
        format_item: Any,
        page_size: int = 10,
        title: str = "",
    ) -> Any | None:
        """分页选择器。"""
        selector = PaginatedSelector(
            items=items,
            format_item=format_item,
            page_size=page_size,
            title=title,
        )
        return await selector.prompt_async()

    def _ensure_session(self) -> None:
        """延迟创建 prompt_toolkit PromptSession。"""
        if self._session is not None:
            return

        completer = FuzzyCompleter(SlashCommandCompleter(self._command_registry))
        completion_style = Style.from_dict({
            "completion-menu": "bg:",
            "completion-menu.completion": "fg:#888888 bg:",
            "completion-menu.completion.current": "fg:#000000 bg:",
            "completion-menu.meta.completion": "fg:#666666 bg:",
            "completion-menu.meta.completion.current": "fg:#333333 bg:",
            "completion-menu.multi-column-meta": "bg:",
            "completion-menu.completion fuzzymatch.inside": "bg:",
            "completion-menu.completion fuzzymatch.inside.character": "bg:",
            "completion-menu.completion fuzzymatch.outside": "fg:#666666 bg:",
            "scrollbar": "bg:",
            "scrollbar.button": "bg:",
        })
        self._session = PromptSession(
            history=InMemoryHistory(),
            completer=completer,
            complete_while_typing=True,
            style=completion_style,
        )

    # ------------------------------------------------------------------
    # 会话历史渲染
    # ------------------------------------------------------------------

    def render_history(self, messages: list[dict]) -> None:
        """渲染历史对话消息列表。"""
        _render_history(self._console, messages)

    # ------------------------------------------------------------------
    # 语音显示
    # ------------------------------------------------------------------

    def on_voice_state_change(self, state: str) -> None:
        """语音状态变化通知。"""
        if self._voice_display is None:
            self._voice_display = VoiceDisplay(self._console)
        if state == "listening":
            self._voice_display.start_listening()
        elif state in ("idle", "error"):
            self._voice_display.stop()

    def on_voice_interim_text(self, text: str) -> None:
        """语音实时转录文本更新。"""
        if self._voice_display is None:
            self._voice_display = VoiceDisplay(self._console)
        self._voice_display.update_interim(text)

    def show_voice_final(self, text: str, timings: dict[str, int]) -> None:
        """展示语音最终识别结果及耗时。"""
        if self._voice_display is None:
            self._voice_display = VoiceDisplay(self._console)
        for step, ms in timings.items():
            self._voice_display.update_timing(step, ms)
        self._voice_display.finish(text)

    def update_voice_timing(self, step: str, ms: int) -> None:
        """更新语音处理某步骤的实时耗时。"""
        if self._voice_display is None:
            self._voice_display = VoiceDisplay(self._console)
        self._voice_display.update_timing(step, ms)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """UI 初始化。"""
        # ANSI 滚动区域（状态栏）
        if self._status_bar_enabled:
            from cli.ansi_status_bar import setup_scroll_region, paint_status_bar
            from prompt_toolkit.output.vt100 import Vt100_Output
            _original_get_size = Vt100_Output.get_size

            def _patched_get_size(self):
                size = _original_get_size(self)
                from prompt_toolkit.data_structures import Size
                return Size(rows=max(size.rows - 1, 2), columns=size.columns)

            Vt100_Output.get_size = _patched_get_size  # type: ignore[assignment]
            setup_scroll_region(status_lines=1)
            paint_status_bar(self._status_bar_renderer)

        # Banner
        default_model = self._config.get("routing", {}).get("default_model", "unknown")
        show_banner(
            console=self._console,
            model=default_model,
            version="0.1.0",
            cwd=str(Path.cwd()),
        )

    def teardown(self) -> None:
        """UI 清理。"""
        if self._tool_display:
            self._tool_display.cleanup()
        self.stop_stage()
        self.flush_thinking()
        self.flush_streaming()
        if self._status_bar_enabled:
            from cli.ansi_status_bar import teardown_scroll_region
            teardown_scroll_region()

    def repaint_status_bar(self) -> None:
        """重绘 ANSI 状态栏。"""
        if not self._status_bar_enabled or not self._status_bar_renderer:
            return
        try:
            from cli.ansi_status_bar import paint_status_bar
            paint_status_bar(self._status_bar_renderer)
        except Exception:
            pass
