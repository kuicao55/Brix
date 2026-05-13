"""VoiceRuntime Protocol 测试。"""

from capability.voice.protocol import VoiceRuntime


def test_voice_runtime_protocol_exists():
    """VoiceRuntime Protocol 可以导入。"""
    assert VoiceRuntime is not None


def test_voice_runtime_protocol_methods():
    """VoiceRuntime Protocol 定义了所有必需方法。"""
    import inspect
    methods = [name for name, _ in inspect.getmembers(VoiceRuntime, predicate=inspect.isfunction)]
    # Protocol 的方法通过 __protocol_attrs__ 或 dir() 获取
    attrs = dir(VoiceRuntime)
    assert "start" in attrs
    assert "stop" in attrs
    assert "is_running" in attrs
    assert "on_voice_input" in attrs
    assert "on_state_change" in attrs
