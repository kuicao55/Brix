"""Response formatting for terminal display."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from cli.stream_renderer import _MarkerMarkdown


def format_response(text: str) -> str:
    """Format an assistant response for terminal output.

    MVP: passthrough.  Future: syntax highlighting, markdown rendering.
    """
    return text


def render_history(console: Console, messages: list[dict]) -> None:
    """用聊天界面的完整格式渲染历史消息列表。

    - assistant 消息：⏺ 标记 + Rich Markdown 渲染（含 tool_calls 显示）
    - tool 消息：工具名称 + 结果预览
    - user 消息：❯ 提示符 + 文本
    """
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "assistant":
            if not content and not msg.get("tool_calls"):
                continue
            # 显示工具调用
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tc_name = tc.get("name", "")
                    if not tc_name and "function" in tc:
                        tc_name = tc["function"].get("name", "")
                    if tc_name:
                        console.print(f"  [dim]Called tool: {tc_name}[/]")
            if content:
                console.print(_MarkerMarkdown(
                    content,
                    marker_text="⏺ ",
                    marker_style="green",
                    console=console,
                ))

        elif role == "tool":
            tc_name = msg.get("name", "tool")
            result_preview = (content[:200] + "...") if content and len(content) > 200 else (content or "(empty)")
            console.print(f"  [dim]{tc_name} -> {result_preview}[/]")

        elif role == "user":
            if not content:
                continue
            prompt = Text("❯ ", style="bold cyan")
            prompt.append(content)
            console.print(prompt)

        console.print()  # 消息间空行
