"""Startup banner for Brix."""

from __future__ import annotations

BRIX_ASCII = r"""
 ██████╗ ██████╗ ██╗██╗  ██╗
 ██╔══██╗██╔══██╗██║╚██╗██╔╝
 ██████╔╝██████╔╝██║ ╚███╔╝
 ██╔══██╗██╔══██╗██║ ██╔██╗
 ██████╔╝██║  ██║██║██╔╝ ██╗
 ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝
"""


def show_banner(model: str, version: str, cwd: str) -> None:
    """Print the startup banner with session info."""
    print(BRIX_ASCII)
    print("  BRIX — Personal AI Agent")
    print()
    print(f"  Model       {model}")
    print(f"  Version     {version}")
    print(f"  Directory   {cwd}")
    print()
    print("  Type /help for commands · Ctrl+C to exit")
    print()
