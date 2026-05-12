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

    - assistant 消息：⏺ 标记 + Rich Markdown 渲染
    - user 消息：❯ 提示符 + 文本
    """
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not content:
            continue

        if role == "assistant":
            console.print(_MarkerMarkdown(
                content,
                marker_text="⏺ ",
                marker_style="green",
                console=console,
            ))
        elif role == "user":
            prompt = Text("❯ ", style="bold cyan")
            prompt.append(content)
            console.print(prompt)

        console.print()  # 消息间空行
