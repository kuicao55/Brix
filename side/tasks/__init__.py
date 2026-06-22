"""Side tasks 集合。"""
from side.tasks.session_title import SessionTitleTask
from side.tasks.tool_summary import ToolSummaryTask
from side.tasks.history_search import HistorySearchTask
from side.tasks.context_compress import ContextCompressTask
from side.tasks.session_summary import SessionSummaryTask
from side.tasks.memory_summary import MemorySummaryTask
from side.tasks.dream import DreamTask

ALL_TASKS = [
    SessionTitleTask(),
    ToolSummaryTask(),
    HistorySearchTask(),
    ContextCompressTask(),
    SessionSummaryTask(),
    MemorySummaryTask(),
    DreamTask(),
]
