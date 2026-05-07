"""Lightweight event registry for the Hook system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class HookEvent:
    """Hook event carrier."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)


class HookRegistry:
    """Lightweight event registration and dispatch center."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[Callable[[HookEvent], None]]] = {}
        self._log: Any = None

    def bind_log(self, log: Any) -> None:
        """Bind a FlowLog instance. All events auto-forward to log.step()."""
        self._log = log

    def register(self, event: str, hook: Callable[[HookEvent], None]) -> None:
        """Register a custom hook for an event."""
        self._hooks.setdefault(event, []).append(hook)

    def fire(self, event: str, **data: Any) -> None:
        """
        Fire an event (synchronous).
        1. Forward to FlowLog.step() if bound.
        2. Call all registered custom hooks.
        """
        if self._log is not None:
            self._log.step(event, **data)

        hook_event = HookEvent(name=event, data=data)
        for hook in self._hooks.get(event, []):
            try:
                hook(hook_event)
            except Exception:
                pass  # one failing hook does not affect others
