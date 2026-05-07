"""In-memory step collector for a single conversation turn."""

from __future__ import annotations

import uuid
from datetime import datetime


class FlowLog:
    """Collects pipeline steps during one _process() call."""

    def __init__(self, user_input: str) -> None:
        self._trace = uuid.uuid4().hex[:8]
        self._ts = datetime.now()
        self._input = user_input
        self._steps: list[dict] = []
        self._model: str = ""
        self._error: str | None = None
        self._t0 = _monotonic_ms()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def step(self, module: str, **kwargs) -> None:
        """Record a pipeline step. Timestamp is captured at call time (step end)."""
        if not module:
            return
        from datetime import datetime
        self._steps.append({"m": module, "at": datetime.now().strftime("%H:%M:%S.%f")[:-3], **kwargs})

    @staticmethod
    def now() -> str:
        """Current timestamp in HH:MM:SS.mmm format."""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def set_model(self, model: str) -> None:
        self._model = model

    def set_error(self, error: str) -> None:
        self._error = error

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def finish(self) -> dict:
        """Return the full log entry as a JSONL-ready dict."""
        ms_total = _monotonic_ms() - self._t0
        llm_calls = sum(1 for s in self._steps
                        if "ms" in s and s.get("m") != "tool_exec")
        tools = sum(1 for s in self._steps if s.get("m") == "tool_exec")
        iters = sum(1 for s in self._steps if s.get("m") == "orch_plan")
        return {
            "ts": self._ts.strftime("%Y-%m-%dT%H:%M:%S"),
            "trace": self._trace,
            "input": self._input,
            "steps": self._steps,
            "model": self._model,
            "iters": iters,
            "tools": tools,
            "llm_calls": llm_calls,
            "ms_total": ms_total,
            "error": self._error,
        }

    def to_text(self) -> str:
        """Return a 3-line human-readable log entry."""
        entry = self.finish()
        ts = self._ts.strftime("%Y-%m-%d %H:%M:%S")
        preview = self._input[:60].replace("\n", " ")
        trace = entry["trace"]

        # Line 1: header
        line1 = f'{ts} [{trace}] "{preview}"'

        # Line 2: step chain
        chain = _format_chain(self._steps)
        line2 = f"  {chain}" if chain else "  (no steps)"

        # Line 3: summary
        status = "ERR" if self._error else "OK"
        line3 = (
            f"  => {entry['ms_total']}ms, "
            f"{entry['llm_calls']} llm, "
            f"{entry['tools']} tool, "
            f"{status}"
        )

        return f"{line1}\n{line2}\n{line3}\n"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _monotonic_ms() -> int:
    """Current time in milliseconds (monotonic)."""
    import time
    return int(time.monotonic() * 1000)


def _format_chain(steps: list[dict]) -> str:
    """Format steps into a compact chain string."""
    parts: list[str] = []
    for s in steps:
        m = s.get("m", "")
        if m == "memory":
            parts.append(f"memory({s.get('msgs', '?')}->{s.get('window', '?')})")
        elif m == "intent":
            via = s.get("via", "")
            ms = s.get("ms", "")
            parts.append(f"intent({s.get('result', '?')},{via},{ms}ms)")
        elif m == "complexity":
            parts.append(f"complexity({s.get('result', '?')})")
        elif m == "router":
            parts.append(f"router({s.get('model', '?')})")
        elif m == "orch_plan":
            it = s.get("iter", "?")
            tools = s.get("tools", [])
            ms = s.get("ms", "")
            tool_str = ",".join(tools) if tools else "none"
            parts.append(f"plan#{it}([{tool_str}],{ms}ms)")
        elif m == "tool_exec":
            name = s.get("name", "?")
            result = str(s.get("result", ""))[:30]
            ms = s.get("ms", "")
            parts.append(f"exec({name}={result},{ms}ms)")
        elif m == "persist":
            parts.append(f"persist({s.get('saved', '?')})")
        else:
            parts.append(m)
    return " -> ".join(parts)
