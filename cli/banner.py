"""Startup banner for Brix."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

BRIX_ASCII = r"""
 ██████╗ ██████╗ ██╗██╗  ██╗
 ██╔══██╗██╔══██╗██║╚██╗██╔╝
 ██████╔╝██████╔╝██║ ╚███╔╝
 ██╔══██╗██╔══██╗██║ ██╔██╗
 ██████╔╝██║  ██║██║██╔╝ ██╗
 ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝
"""


def show_banner(console: Console, model: str, version: str, cwd: str) -> None:
    """Print the startup banner with session info using Rich Console."""
    console.print(BRIX_ASCII, style="bold cyan")
    console.print("  BRIX — Personal AI Agent\n", style="dim")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column(style="white")
    table.add_row("Model", model)
    table.add_row("Version", version)
    table.add_row("Directory", cwd)
    console.print(table)
    console.print()
    console.print("  Type /help for commands · Ctrl+C to exit\n", style="dim")
