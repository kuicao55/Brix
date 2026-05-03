"""JSON-backed conversation history storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MemoryStorage:
    """Persist conversation history to a JSON file."""

    def __init__(self, path: str = "data/memory.json") -> None:
        self._path = Path(path)
        self._messages: list[dict[str, Any]] = []
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        """Append a message with an ISO-8601 timestamp."""
        self._messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Return recent messages, optionally capped to *limit* entries."""
        if limit is None:
            return list(self._messages)
        return list(self._messages[-limit:])

    def clear(self) -> None:
        """Empty the in-memory history."""
        self._messages.clear()

    def save(self) -> None:
        """Write current history to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as fh:
            json.dump(self._messages, fh, indent=2)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load history from disk if the file exists."""
        if not self._path.exists():
            return
        try:
            with open(self._path) as fh:
                data = json.load(fh)
            if isinstance(data, list):
                self._messages = data
        except (json.JSONDecodeError, OSError):
            self._messages = []
