"""Tool registry and runner."""

from __future__ import annotations

from capability.base import Tool


class ToolRunner:
    """Registers tools and dispatches execution by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    async def run(self, tool_name: str, params: dict) -> str:
        """Execute a registered tool by name."""
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ValueError(f"Unknown tool: {tool_name}")
        return await tool.execute(**params)

    def get_tool_schemas(self) -> list[dict]:
        """Return OpenAI-compatible schemas for all registered tools."""
        return [tool.to_openai_schema() for tool in self._tools.values()]
