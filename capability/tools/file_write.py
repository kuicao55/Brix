"""文件写入工具 — 仅限写入 memory/data/ 目录。"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from capability.base import Tool


class FileWriteTool(Tool):
    """将内容写入 memory/data/ 下的文件。"""

    def __init__(self, allowed_root: Path | None = None) -> None:
        self._allowed_root = allowed_root or (
            Path(__file__).resolve().parent.parent.parent / "memory" / "data"
        )

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return (
            "将内容写入文件。只能写入 memory/data/ 目录下的文件。"
            "用于创建 soul.md、user.md 等记忆文件。"
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件相对路径（相对于 memory/data/），如 'soul.md' 或 'user.md'",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的完整内容",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, **params) -> str:
        rel_path = params.get("path", "")
        content = params.get("content", "")
        target = (self._allowed_root / rel_path).resolve()
        # Security: must stay within allowed_root (使用 is_relative_to 防止前缀碰撞攻击)
        if not target.is_relative_to(self._allowed_root.resolve()):
            return "Error: 路径被拒绝 — 只能写入 memory/data/ 目录"
        # Security: reject symlinks
        if target.exists() and target.is_symlink():
            return "Error: 拒绝写入符号链接"
        # Atomic write
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent), prefix=".file-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(target))
        except Exception as e:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return f"Error: 写入失败 — {e}"
        return f"写入成功: {rel_path}"
