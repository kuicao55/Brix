"""Response formatting for terminal display."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape as markup_escape
from rich.text import Text

from cli.stream_renderer import _MarkerMarkdown
from cli.thinking_renderer import _COLLAPSE_THRESHOLD, _MARKER, _MarkerText
from cli.tool_display import ToolDisplay


def format_response(text: str) -> str:
    """Format an assistant response for terminal output.

    MVP: passthrough.  Future: syntax highlighting, markdown rendering.
    """
    return text


def _extract_tool_call(tc: dict) -> tuple[str, dict]:
    """从 tool_call 字典中提取 name 和 input，兼容 flat 和 function-wrapped 格式。"""
    tc_name = tc.get("name", "")
    tc_input = tc.get("input", {})
    if not tc_name and "function" in tc:
        func = tc["function"]
        tc_name = func.get("name", "")
        args = func.get("arguments", {})
        if isinstance(args, str):
            import json
            try:
                tc_input = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                tc_input = {}
        else:
            tc_input = args
    return tc_name, tc_input if isinstance(tc_input, dict) else {}


def _render_reasoning(console: Console, reasoning: str) -> None:
    """静态渲染 thinking/reasoning 内容，与实时 ThinkingRenderer 的 flush 样式一致。"""
    if len(reasoning) > _COLLAPSE_THRESHOLD:
        summary = Text()
        summary.append(_MARKER, style="dim cyan")
        summary.append("Thought ({} chars)".format(len(reasoning)), style="dim")
        console.print(summary)
    else:
        renderable = _MarkerText(
            reasoning,
            marker_text=_MARKER,
            marker_style="dim cyan",
            content_style="dim",
            console=console,
        )
        console.print(renderable)


def _render_tool_result(console: Console, tool_name: str, content: str) -> None:
    """渲染工具结果行，样式与 ToolDisplay.show_tool_result 一致（不含 spinner）。"""
    safe_name = markup_escape(str(tool_name))
    icon = ToolDisplay.TOOL_ICONS.get(tool_name, "\U0001f527")
    preview = (content or "")[:200].replace("\n", " ")
    if len(content or "") > 200:
        preview += "\u2026"

    text = Text()
    text.append("\u23bf ", style="dim")
    text.append("{} ".format(icon), style="dim")
    text.append(safe_name, style="tool.name")
    text.append("  \u2713", style="green")
    text.append("  0ms", style="dim cyan")
    console.print(text)


def render_history(console: Console, messages: list[dict]) -> None:
    """用聊天界面的完整格式渲染历史消息列表。

    复用 ToolDisplay / ThinkingRenderer 的渲染逻辑，保持与实时对话一致的样式：
    - assistant 消息：∴ thinking + Rich Panel 工具调用 + ⏺ 文本渲染
    - tool 消息：⎯ 图标 name ✓ 结果行
    - user 消息：❯ 提示符 + 文本（过滤 Skill 注入的 prompt）
    """
    tool_display = ToolDisplay(console)
    # 预处理：标记 Skill 注入的 user message（前一条 tool 消息 content 以 "Launching skill:" 开头）
    _skill_injected_indices: set[int] = set()
    for i, msg in enumerate(messages):
        if msg.get("role") == "user" and i > 0:
            prev = messages[i - 1]
            if prev.get("role") == "tool" and (prev.get("content") or "").startswith("Launching skill:"):
                _skill_injected_indices.add(i)

    for idx, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "assistant":
            if not content and not msg.get("tool_calls") and not msg.get("reasoning_content"):
                continue

            # 显示 thinking/reasoning
            reasoning = msg.get("reasoning_content")
            if reasoning:
                _render_reasoning(console, reasoning)

            # 显示文本内容（在工具调用之前）
            if content:
                console.print(_MarkerMarkdown(
                    content,
                    marker_text="\u23fa ",
                    marker_style="green",
                    console=console,
                ))

            # 显示工具调用 panel（在文本之后）
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tc_name, tc_input = _extract_tool_call(tc)
                    if tc_name:
                        tool_display.show_tool_start(tc_name, tc_input)

        elif role == "tool":
            tc_name = msg.get("name", "tool")
            _render_tool_result(console, tc_name, content)

        elif role == "user":
            if not content:
                continue
            # 过滤 Skill 注入的内部 prompt（用户不需要看到）
            if idx in _skill_injected_indices:
                continue
            prompt = Text("\u276f ", style="bold cyan")
            prompt.append(content)
            console.print(prompt)

        console.print()  # 消息间空行
