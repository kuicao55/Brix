"""文件编辑工具 — 对 memory/data/ 下的已有文件做文本替换。"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from capability.base import Tool


class FileEditTool(Tool):
    """对 memory/data/ 下的文件进行文本替换。"""

    def __init__(self, allowed_root: Path | None = None) -> None:
        self._allowed_root = allowed_root or (
            Path(__file__).resolve().parent.parent.parent / "memory" / "data"
        )

    @property
    def name(self) -> str:
        return "file_edit"

    @property
    def description(self) -> str:
        return (
            "编辑已有文件中的文本。只能编辑 memory/data/ 目录下的文件。"
            "使用精确文本匹配进行替换，适合更新 user.md 中的用户信息。"
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件相对路径（相对于 memory/data/）",
                },
                "old_text": {
                    "type": "string",
                    "description": "要替换的原始文本（必须精确匹配）",
                },
                "new_text": {
                    "type": "string",
                    "description": "替换后的新文本",
                },
            },
            "required": ["path", "old_text", "new_text"],
        }

    async def execute(self, **params) -> str:
        rel_path = params.get("path", "")
        old_text = params.get("old_text", "")
        new_text = params.get("new_text", "")
        target = (self._allowed_root / rel_path).resolve()
        # Security checks (使用 is_relative_to 防止前缀碰撞攻击)
        if not target.is_relative_to(self._allowed_root.resolve()):
            return "Error: 路径被拒绝 — 只能编辑 memory/data/ 目录"
        if not target.exists():
            return f"Error: 文件不存在 — {rel_path}"
        if target.is_symlink():
            return "Error: 拒绝编辑符号链接"
        # Read and check
        content = target.read_text(encoding="utf-8")
        count = content.count(old_text)
        if count == 0:
            return "Error: 未找到匹配文本 — 请确认 old_text 精确匹配"
        if count > 1:
            return f"Error: 找到 {count} 处匹配 — 请提供更多上下文使 old_text 唯一"
        # Replace and atomic write
        new_content = content.replace(old_text, new_text, 1)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent), prefix=".file-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(target))
        except Exception as e:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return f"Error: 写入失败 — {e}"
        return f"编辑成功: {rel_path}"
