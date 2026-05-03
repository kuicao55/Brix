"""JSON-backed conversation history storage."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
        """Write current history to disk using atomic temp-file-then-rename."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent, suffix=".tmp", prefix=".memory-"
        )
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                json.dump(self._messages, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(self._path))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load history from disk if the file exists."""
        if not self._path.exists():
            return
        try:
            self._messages = json.loads(self._path.read_text())
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Corrupt memory file {self._path}: {e}. Starting fresh.")
            self._messages = []
