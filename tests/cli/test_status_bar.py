"""StatusBarRenderer 测试。"""
from __future__ import annotations

from cli.status_bar import StatusBarRenderer
from plugins.status_bar.plugin import StatusBarPlugin


def _make_renderer(plugin: StatusBarPlugin | None = None) -> StatusBarRenderer:
    """创建测试用 renderer。"""
    if plugin is None:
        plugin = StatusBarPlugin(side_model="test-model")
    return StatusBarRenderer(plugin)


def test_get_toolbar_idle():
    """空闲状态显示 idle。"""
    renderer = _make_renderer()
    toolbar = renderer.get_toolbar()
    text = "".join(t for _, t in toolbar)
    assert "test-model" in text
    assert "idle" in text


def test_get_toolbar_running():
    """运行状态显示 spinner + 任务名。"""
    plugin = StatusBarPlugin(side_model="qwen")
    plugin.on_task_start("dream")
    renderer = _make_renderer(plugin)
    toolbar = renderer.get_toolbar()
    text = "".join(t for _, t in toolbar)
    assert "qwen" in text
    assert "dream" in text


def test_get_toolbar_completed():
    """完成状态显示勾号 + 任务名 + 耗时。"""
    plugin = StatusBarPlugin()
    plugin.on_task_start("dream")
    plugin.on_task_end("dream", "completed", 1.2)
    renderer = _make_renderer(plugin)
    toolbar = renderer.get_toolbar()
    text = "".join(t for _, t in toolbar)
    assert "\u2713" in text  # ✓
    assert "dream" in text
    assert "1.2s" in text


def test_get_toolbar_error():
    """错误状态显示叉号 + 任务名。"""
    plugin = StatusBarPlugin()
    plugin.on_task_start("dream")
    plugin.on_task_end("dream", "error")
    renderer = _make_renderer(plugin)
    toolbar = renderer.get_toolbar()
    text = "".join(t for _, t in toolbar)
    assert "\u2717" in text  # ✗
    assert "dream" in text


def test_get_toolbar_returns_list():
    """get_toolbar 返回 (style, text) 元组列表。"""
    renderer = _make_renderer()
    toolbar = renderer.get_toolbar()
    assert isinstance(toolbar, list)
    for item in toolbar:
        assert isinstance(item, tuple)
        assert len(item) == 2
        assert isinstance(item[0], str)
        assert isinstance(item[1], str)


def test_get_toolbar_text_idle():
    """空闲状态返回 model | idle。"""
    renderer = _make_renderer()
    text = renderer.get_toolbar_text()
    assert "test-model" in text
    assert "idle" in text
    assert "|" in text


def test_get_toolbar_text_running():
    """运行状态包含 spinner 和任务名。"""
    plugin = StatusBarPlugin(side_model="qwen")
    plugin.on_task_start("dream")
    renderer = _make_renderer(plugin)
    text = renderer.get_toolbar_text()
    assert "qwen" in text
    assert "dream" in text


def test_get_toolbar_text_completed():
    """完成状态包含勾号和耗时。"""
    plugin = StatusBarPlugin()
    plugin.on_task_start("dream")
    plugin.on_task_end("dream", "completed", 1.2)
    renderer = _make_renderer(plugin)
    text = renderer.get_toolbar_text()
    assert "\u2713" in text
    assert "dream" in text
    assert "1.2s" in text


def test_get_toolbar_text_error():
    """错误状态包含叉号。"""
    plugin = StatusBarPlugin()
    plugin.on_task_start("dream")
    plugin.on_task_end("dream", "error")
    renderer = _make_renderer(plugin)
    text = renderer.get_toolbar_text()
    assert "\u2717" in text
    assert "dream" in text


def test_get_toolbar_text_single_line():
    """返回值是单行字符串，不含换行符。"""
    plugin = StatusBarPlugin(side_model="test-model")
    plugin.on_task_start("a" * 200)
    renderer = _make_renderer(plugin)
    text = renderer.get_toolbar_text()
    assert "\n" not in text
