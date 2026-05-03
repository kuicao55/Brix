"""Read local file contents with a size limit."""

from __future__ import annotations

from pathlib import Path

from capability.base import Tool

_MAX_BYTES = 100_000  # 100 KB limit


class FileReadTool(Tool):
    """Read the contents of a local file."""

    # Subclass or override in tests to change allowed root.
    allowed_root: Path = Path.cwd()

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

        p_raw = Path(path_str).expanduser()

        # Check for symlinks before resolving (resolve() follows symlinks)
        check = p_raw
        while check != check.parent:
            if check.is_symlink():
                return "Error: symlinks not allowed"
            check = check.parent

        p = p_raw.resolve()
        root = self.allowed_root.resolve()

        # Check path is within allowed root
        if not p.is_relative_to(root):
            return "Error: path must be within project directory"

        if not p.exists():
            return f"Error: file not found: {path_str}"
        if not p.is_file():
            return f"Error: not a file: {path_str}"
        try:
            with open(p, "r") as f:
                content = f.read(_MAX_BYTES + 1)  # read one extra byte to detect truncation
            if len(content) > _MAX_BYTES:
                return content[:_MAX_BYTES] + "\n... (truncated)"
            return content
        except Exception as exc:
            return f"Error reading file: {exc}"
