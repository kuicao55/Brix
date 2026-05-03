"""Abstract base class for tools."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Tool(ABC):
    """Base class that all tools must inherit."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""
        ...

    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema describing the tool's parameters."""
        ...

    @abstractmethod
    async def execute(self, **params) -> str:
        """Execute the tool and return a string result."""
        ...

    def to_openai_schema(self) -> dict:
        """Return OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
