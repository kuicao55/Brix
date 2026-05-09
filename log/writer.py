"""File I/O for flow logs — JSONL storage and reading."""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from pathlib import Path

LOG_DIR = Path("log/data")
JSONL_PATH = LOG_DIR / "brix.jsonl"

logger = logging.getLogger(__name__)


def ensure_log_dir() -> None:
    """Create the log directory if it doesn't exist."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def write_jsonl(entry: dict) -> None:
    """Append one JSON line to the JSONL log file."""
    try:
        ensure_log_dir()
        with open(JSONL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        logger.warning("Failed to write JSONL log: %s", e)


def flush_log(flow_log) -> None:
    """Serialize a FlowLog to the JSONL file."""
    entry = flow_log.finish()
    write_jsonl(entry)


def read_all() -> list[dict]:
    """Read all entries from the JSONL file."""
    if not JSONL_PATH.exists():
        return []
    entries = []
    try:
        with open(JSONL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError as e:
        logger.warning("Failed to read JSONL log: %s", e)
    return entries


def read_entry(index: int) -> dict | None:
    """Read a single entry by 1-based index. Returns None if not found."""
    entries = read_all()
    if 1 <= index <= len(entries):
        return entries[index - 1]
    return None


def entry_count() -> int:
    """Count total entries in the JSONL file."""
    if not JSONL_PATH.exists():
        return 0
    try:
        with open(JSONL_PATH, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def format_compact_list(entries: list[dict], start_index: int) -> str:
    """Format entries as a compact numbered list for /log."""
    lines = []
    for i, entry in enumerate(entries, start=start_index):
        ts = entry.get("ts", "?")
        trace = entry.get("trace", "?")
        preview = entry.get("input", "")[:50].replace("\n", " ")
        ms = entry.get("ms_total", 0)
        error = entry.get("error")
        status = "ERR" if error else "OK"
        lines.append(f"  #{i}  {ts} [{trace}]  {ms}ms  {status}  \"{preview}\"")
    return "\n".join(lines)


def _parse_ts(ts: str, ref_date: str = ""):
    """Parse a timestamp string into a datetime, handling multiple formats.

    For time-only formats (HH:MM:SS), use ref_date (YYYY-MM-DD) as the date part
    to avoid cross-year comparison issues.
    """
    from datetime import datetime
    # Full datetime
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    # Time-only — attach reference date
    if ref_date:
        for fmt in ("%H:%M:%S.%f", "%H:%M:%S"):
            try:
                t = datetime.strptime(ts, fmt)
                d = datetime.strptime(ref_date, "%Y-%m-%d")
                return d.replace(hour=t.hour, minute=t.minute,
                                 second=t.second, microsecond=t.microsecond)
            except ValueError:
                continue
    return None


def _calc_delta(t1: str, t2: str, ref_date: str = "") -> float | None:
    """Calculate seconds between two timestamps."""
    d1 = _parse_ts(t1, ref_date)
    d2 = _parse_ts(t2, ref_date)
    if d1 and d2:
        return round((d2 - d1).total_seconds(), 1)
    return None


def format_detail(entry: dict) -> str:
    """Format a single entry as a detailed, readable log."""
    ts = entry.get("ts", "?")
    trace = entry.get("trace", "?")
    inp = entry.get("input", "")
    model = entry.get("model", "?")
    ms_total = entry.get("ms_total", 0)
    llm_calls = entry.get("llm_calls", 0)
    tools = entry.get("tools", 0)
    iters = entry.get("iters", 0)
    error = entry.get("error")
    steps = entry.get("steps", [])

    status = "ERR" if error else "OK"
    sep = "-" * 60

    lines = [
        sep,
        f"  Trace:  {trace}",
        f"  Time:   {ts}",
        f"  Input:  {inp}",
        f"  Model:  {model}",
        f"  Status: {status}",
        sep,
    ]

    # Compute per-step durations: at[i] - at[i-1] = time spent on step i
    # (at is recorded at step end, so delta = this step's actual duration)
    ref_date = ts.split("T")[0] if "T" in ts else ""
    step_durations: list[float | None] = []
    for i, s in enumerate(steps):
        if i == 0:
            # First step: delta from request start to first step end
            step_durations.append(_calc_delta(ts, s.get("at", ""), ref_date))
        else:
            prev_at = steps[i - 1].get("at", "")
            curr_at = s.get("at", "")
            step_durations.append(_calc_delta(prev_at, curr_at, ref_date))

    # Step descriptions
    _desc = {
        "memory": "从存储加载历史记录，裁剪上下文窗口",
        "intent": "调用 LLM 分类用户意图 (chat/task/tool_use)",
        "complexity": "基于关键词规则评估请求复杂度",
        "router": "根据意图和复杂度选择最佳模型",
        "orch_plan": "调用 LLM 生成回复 (streaming)",
        "tool_exec": "执行工具调用并返回结果",
        "persist": "将本轮对话保存到存储",
    }

    # Step-by-step detail
    for i, s in enumerate(steps, 1):
        m = s.get("m", "?")
        at = s.get("at", "")
        dur = step_durations[i - 1]

        # Header: [N] module  @timestamp  X.Xs
        at_str = f"  @{at}" if at else ""
        dur_str = f"  {dur:.1f}s" if dur is not None and dur >= 0 else ""
        lines.append(f"  [{i}] {m}{at_str}{dur_str}")

        # Description
        desc = _desc.get(m)
        if desc:
            lines.append(f"      {desc}")

        for k, v in s.items():
            if k in ("m", "at"):
                continue
            if k in ("prompt", "context_window") and isinstance(v, list):
                lines.append(f"      {k}:")
                for msg in v:
                    role = msg.get("role", "?")
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        preview = content[:120].replace("\n", "\\n")
                        if len(content) > 120:
                            preview += "..."
                        lines.append(f"        [{role}] {preview}")
                    elif isinstance(content, list):
                        for block in content:
                            btype = block.get("type", "?")
                            if btype == "text":
                                txt = block.get("text", "")[:100]
                                lines.append(f"        [{role}/{btype}] {txt}")
                            elif btype == "tool_use":
                                lines.append(f"        [{role}/{btype}] {block.get('name', '?')}")
                            elif btype == "tool_result":
                                lines.append(f"        [{role}/{btype}] {block.get('tool_use_id', '?')}")
                            else:
                                lines.append(f"        [{role}/{btype}]")
                    else:
                        lines.append(f"        [{role}] {content}")
            else:
                lines.append(f"      {k}: {v}")
        lines.append("")

    if error:
        lines.append(f"  ERROR: {error}")
        lines.append("")

    # Summary
    lines.append(sep)
    lines.append(
        f"  Total: {ms_total}ms | LLM calls: {llm_calls} | "
        f"Tools: {tools} | Iterations: {iters}"
    )
    lines.append(sep)

    return "\n".join(lines)
