"""用户记忆管理器 — 负责 user.md 的读写。"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


class UserMemoryManager:
    """管理 memory/data/user.md 文件。"""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "user.md"

    def exists(self) -> bool:
        """判断 user.md 是否存在且非空。"""
        return self._path.exists() and self._path.stat().st_size > 0

    def load(self) -> str:
        """加载 user.md 内容，文件不存在时返回空字符串。"""
        if not self._path.exists():
            return ""
        try:
            return self._path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def save(self, content: str) -> None:
        """原子保存内容到 user.md：临时文件 + fsync + rename。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".user-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = -1  # fd 已由 os.fdopen 接管
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(self._path))
        except Exception:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
