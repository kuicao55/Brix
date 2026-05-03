"""Orchestrator context and engine protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolRunner(Protocol):
    """Protocol for something that can execute tool calls."""

    async def run(self, tool_name: str, params: dict) -> str:
        ...

    def get_tool_schemas(self) -> list[dict]:
        ...


@dataclass
class OrchestratorContext:
    """Mutable context passed through the orchestrator run."""

    history: list[dict] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)
    tool_runner: Any = None
    llm_client: Any = None
    model: str = ""


@runtime_checkable
class OrchestratorEngine(Protocol):
    """Protocol that all orchestrator implementations must satisfy."""

    async def run(self, user_input: str, context: OrchestratorContext) -> str:
        ...
