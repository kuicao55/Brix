"""Read local file contents with a size limit."""

from __future__ import annotations

from pathlib import Path

from capability.base import Tool

_MAX_BYTES = 100_000  # 100 KB limit


class FileReadTool(Tool):
    """Read the contents of a local file."""

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return "Read the contents of a local file."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                }
            },
            "required": ["path"],
        }

    async def execute(self, **params) -> str:
        path_str = params.get("path", "")
        if not path_str:
            return "Error: path is required"
        file_path = Path(path_str)
        if not file_path.exists():
            return f"Error: file not found: {path_str}"
        if not file_path.is_file():
            return f"Error: not a file: {path_str}"
        try:
            content = file_path.read_text(encoding="utf-8")
            if len(content) > _MAX_BYTES:
                content = content[:_MAX_BYTES] + "\n... (truncated)"
            return content
        except Exception as exc:
            return f"Error reading file: {exc}"
