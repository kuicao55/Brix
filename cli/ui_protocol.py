"""UIAdapter Protocol — UI 抽象层接口定义。

所有 UI 操作的统一接口。换 UI 时只需实现此 Protocol，核心逻辑无需改动。

样式约定：所有 style 参数使用语义化标签：
- "success" → 绿色/成功
- "error"   → 红色/错误
- "muted"   → 灰色/次要信息
- "accent"  → 高亮/强调
- "warning" → 黄色/警告
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class UIAdapter(Protocol):
    """UI 抽象层 — 所有 UI 操作的接口。

    换 UI 时只需实现此 Protocol，核心逻辑无需改动。
    """

    # ------------------------------------------------------------------
    # 一次性输出
    # ------------------------------------------------------------------

    def print(self, text: str, style: str = "") -> None:
        """打印一行文本（语义化样式标签）。"""
        ...

    def print_markdown(self, markdown: str) -> None:
        """渲染并打印 markdown 内容。"""
        ...

    # ------------------------------------------------------------------
    # Streaming 渲染（逐 token 推送）
    # ------------------------------------------------------------------

    def start_thinking(self) -> None:
        """开始 thinking/reasoning 内容块。"""
        ...

    def push_thinking_delta(self, text: str) -> None:
        """推送 thinking 文本增量。"""
        ...

    def flush_thinking(self) -> None:
        """结束 thinking 内容块。"""
        ...

    def start_streaming(self) -> None:
        """开始正式回复的流式渲染。"""
        ...

    def push_text_delta(self, text: str) -> None:
        """推送回复文本增量。"""
        ...

    def flush_streaming(self) -> None:
        """结束流式渲染，确保所有内容输出完毕。"""
        ...

    # ------------------------------------------------------------------
    # Tool 展示
    # ------------------------------------------------------------------

    def show_tool_start(self, name: str, input_data: dict) -> None:
        """展示工具调用开始。"""
        ...

    def show_tool_result(
        self, name: str, result: str, ms: int, is_error: bool = False
    ) -> None:
        """展示工具调用结果。"""
        ...

    # ------------------------------------------------------------------
    # 状态指示
    # ------------------------------------------------------------------

    def update_stage(self, stage: str, detail: str = "") -> None:
        """更新当前处理阶段指示器。"""
        ...

    def stop_stage(self) -> None:
        """停止阶段指示器。"""
        ...

    # ------------------------------------------------------------------
    # 交互式输入
    # ------------------------------------------------------------------

    async def prompt_async(self, prefix: str = "") -> str:
        """异步等待用户输入。"""
        ...

    async def select_paginated(
        self,
        items: list,
        format_item: Any,
        page_size: int = 10,
        title: str = "",
    ) -> Any | None:
        """分页选择器（用于 /resume、/model 等交互命令）。"""
        ...

    # ------------------------------------------------------------------
    # 会话历史渲染
    # ------------------------------------------------------------------

    def render_history(self, messages: list[dict]) -> None:
        """渲染历史对话消息列表。"""
        ...

    # ------------------------------------------------------------------
    # 语音显示
    # ------------------------------------------------------------------

    def on_voice_state_change(self, state: str) -> None:
        """语音状态变化通知（idle/listening/processing/speaking/error）。"""
        ...

    def on_voice_interim_text(self, text: str) -> None:
        """语音实时转录文本更新。"""
        ...

    def show_voice_final(self, text: str, timings: dict[str, int]) -> None:
        """展示语音最终识别结果及耗时。"""
        ...

    def update_voice_timing(self, step: str, ms: int) -> None:
        """更新语音处理某步骤的实时耗时（如 STT、Cleanup）。"""
        ...

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """UI 初始化（如 ANSI 滚动区域、banner 显示）。"""
        ...

    def teardown(self) -> None:
        """UI 清理。"""
        ...
