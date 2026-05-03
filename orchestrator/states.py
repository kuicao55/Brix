"""Orchestrator state definitions."""

from __future__ import annotations

from enum import Enum


class OrchestratorState(str, Enum):
    """States for the orchestrator state machine."""

    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    RESPONDING = "responding"
