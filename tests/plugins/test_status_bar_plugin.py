"""StatusBarPlugin 测试。"""
from __future__ import annotations

from plugins.status_bar import TaskStatus
from plugins.status_bar.plugin import StatusBarPlugin


def test_on_task_start():
    """on_task_start 将任务标记为 RUNNING。"""
    plugin = StatusBarPlugin(side_model="test-model")
    plugin.on_task_start("dream")
    status = plugin.get_status()
    assert len(status.tasks) == 1
    assert status.tasks[0].name == "dream"
    assert status.tasks[0].status == TaskStatus.RUNNING


def test_on_task_end_completed():
    """on_task_end(completed) 将任务标记为 COMPLETED。"""
    plugin = StatusBarPlugin()
    plugin.on_task_start("dream")
    plugin.on_task_end("dream", "completed", 1.5)
    status = plugin.get_status()
    assert status.tasks[0].status == TaskStatus.COMPLETED
    assert status.tasks[0].elapsed_seconds == 1.5


def test_on_task_end_error():
    """on_task_end(error) 将任务标记为 ERROR。"""
    plugin = StatusBarPlugin()
    plugin.on_task_start("dream")
    plugin.on_task_end("dream", "error", 0.5)
    status = plugin.get_status()
    assert status.tasks[0].status == TaskStatus.ERROR


def test_get_status_returns_snapshot():
    """get_status 返回快照，不影响内部状态。"""
    plugin = StatusBarPlugin(side_model="model")
    plugin.on_task_start("task1")
    status1 = plugin.get_status()
    plugin.on_task_end("task1", "completed")
    status2 = plugin.get_status()
    # status1 是快照，不应被后续修改影响
    assert status1.tasks[0].status == TaskStatus.RUNNING
    assert status2.tasks[0].status == TaskStatus.COMPLETED


def test_running_tasks_filter():
    """running_tasks 只返回 RUNNING 状态的任务。"""
    plugin = StatusBarPlugin()
    plugin.on_task_start("a")
    plugin.on_task_start("b")
    plugin.on_task_end("a", "completed")
    status = plugin.get_status()
    assert len(status.running_tasks) == 1
    assert status.running_tasks[0].name == "b"


def test_completed_tasks_filter():
    """completed_tasks 只返回 COMPLETED 状态的任务。"""
    plugin = StatusBarPlugin()
    plugin.on_task_start("a")
    plugin.on_task_start("b")
    plugin.on_task_end("a", "completed")
    plugin.on_task_end("b", "error")
    status = plugin.get_status()
    assert len(status.completed_tasks) == 1
    assert status.completed_tasks[0].name == "a"


def test_error_tasks_filter():
    """error_tasks 只返回 ERROR 状态的任务。"""
    plugin = StatusBarPlugin()
    plugin.on_task_start("a")
    plugin.on_task_end("a", "error")
    status = plugin.get_status()
    assert len(status.error_tasks) == 1
    assert status.error_tasks[0].name == "a"


def test_reset_clears_all():
    """reset() 清空所有任务状态。"""
    plugin = StatusBarPlugin()
    plugin.on_task_start("a")
    plugin.on_task_end("a", "completed")
    plugin.reset()
    status = plugin.get_status()
    assert len(status.tasks) == 0


def test_multiple_tasks():
    """多个任务同时存在，状态互不影响。"""
    plugin = StatusBarPlugin(side_model="qwen")
    plugin.on_task_start("dream")
    plugin.on_task_start("session_title")
    plugin.on_task_end("dream", "completed", 2.0)
    status = plugin.get_status()
    assert status.side_model == "qwen"
    assert len(status.tasks) == 2
    names = {t.name for t in status.tasks}
    assert names == {"dream", "session_title"}
