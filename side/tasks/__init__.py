"""Side tasks 集合。"""
from side.tasks.session_title import SessionTitleTask
from side.tasks.tool_summary import ToolSummaryTask
from side.tasks.pref_detection import PrefDetectionTask
from side.tasks.history_search import HistorySearchTask
from side.tasks.voice_cleanup import VoiceCleanupTask
from side.tasks.context_compress import ContextCompressTask
from side.tasks.session_summary import SessionSummaryTask

ALL_TASKS = [
    SessionTitleTask(),
    ToolSummaryTask(),
    PrefDetectionTask(),
    HistorySearchTask(),
    VoiceCleanupTask(),
    ContextCompressTask(),
    SessionSummaryTask(),
]
