"""灵魂文件管理器 — 负责 soul.md 的读写。"""
from __future__ import annotations

from pathlib import Path


class SoulManager:
    """管理 memory/data/soul.md 文件。"""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "soul.md"

    def exists(self) -> bool:
        """判断 soul.md 是否存在且非空。"""
        return self._path.exists() and self._path.stat().st_size > 0

    def load(self) -> str:
        """加载 soul.md 内容，文件不存在时返回空字符串。"""
        if not self._path.exists():
            return ""
        try:
            return self._path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def save(self, content: str) -> None:
        """保存内容到 soul.md。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(content, encoding="utf-8")
