"""Brix terminal theme for Rich."""

from __future__ import annotations

from rich.style import Style
from rich.theme import Theme

BRIX_THEME = Theme({
    "markdown.h1": Style(bold=True, color="cyan"),
    "markdown.h2": Style(bold=True, color="bright_white"),
    "markdown.h3": Style(color="blue"),
    "markdown.code": Style(color="green"),
    "markdown.code_block": Style(bgcolor="grey11"),
    "markdown.link": Style(color="blue", underline=True),
    "markdown.em": Style(italic=True, color="magenta"),
    "markdown.strong": Style(bold=True, color="yellow"),
    "markdown.blockquote": Style(color="grey50"),
    "tool.border": Style(color="grey50"),
    "tool.name": Style(bold=True, color="cyan"),
    "tool.success": Style(color="green"),
    "tool.error": Style(color="red"),
    "spinner.active": Style(color="blue"),
    "spinner.done": Style(color="green"),
    "spinner.failed": Style(color="red"),
    "stage.name": Style(dim=True, color="white"),
    "stage.time": Style(dim=True, color="cyan"),
    "stage.detail": Style(dim=True, color="grey50"),
    "status_bar.model": Style(dim=True, color="white"),
    "status_bar.running": Style(color="cyan"),
    "status_bar.completed": Style(color="green"),
    "status_bar.error": Style(color="red"),
    "status_bar.idle": Style(dim=True, color="grey50"),
})
