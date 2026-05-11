"""日志查看功能 — 获取最近日志、格式化详情。

直接调用 log.writer 模块，不依赖 MemoryProvider。
"""

from __future__ import annotations

from log.writer import entry_count, format_detail, read_all


def get_recent_logs(limit: int = 20) -> list[dict]:
    """返回最近 N 条日志条目（最新在前）。

    每个 dict 包含: ts, trace, input, ms_total, error 等。
    空列表表示暂无日志。
    """
    total = entry_count()
    if total == 0:
        return []
    return read_all()[-limit:][::-1]


def get_log_detail(entry: dict) -> str:
    """返回单条日志的格式化详情文本。"""
    return format_detail(entry)
