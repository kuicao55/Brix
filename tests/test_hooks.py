"""Tests for the Hook event registry."""

from hooks.registry import HookEvent, HookRegistry


class TestHookEvent:
    def test_default_data(self):
        e = HookEvent(name="test")
        assert e.name == "test"
        assert e.data == {}

    def test_with_data(self):
        e = HookEvent(name="intent", data={"result": "chat", "ms": 100})
        assert e.data["result"] == "chat"


class TestHookRegistry:
    def test_init_empty(self):
        r = HookRegistry()
        assert r._hooks == {}
        assert r._log is None

    def test_bind_log(self):
        r = HookRegistry()
        log = object()  # sentinel
        r.bind_log(log)
        assert r._log is log

    def test_fire_without_log(self):
        """fire() with no bound log should not raise."""
        r = HookRegistry()
        r.fire("intent", result="chat")  # should be a no-op

    def test_fire_forwards_to_log(self):
        """fire() should call log.step() with same args."""
        class FakeLog:
            def __init__(self):
                self.calls = []

            def step(self, module, **kwargs):
                self.calls.append((module, kwargs))

        log = FakeLog()
        r = HookRegistry()
        r.bind_log(log)
        r.fire("intent", result="chat", via="llm", ms=100)

        assert len(log.calls) == 1
        assert log.calls[0] == ("intent", {"result": "chat", "via": "llm", "ms": 100})

    def test_register_custom_hook(self):
        """Custom hooks should be called on fire()."""
        called = []
        r = HookRegistry()
        r.register("intent", lambda e: called.append(e))

        r.fire("intent", result="chat")

        assert len(called) == 1
        assert called[0].name == "intent"
        assert called[0].data == {"result": "chat"}

    def test_multiple_hooks_order(self):
        """Multiple hooks for the same event fire in registration order."""
        order = []
        r = HookRegistry()
        r.register("test", lambda e: order.append("first"))
        r.register("test", lambda e: order.append("second"))

        r.fire("test")

        assert order == ["first", "second"]

    def test_hook_only_fires_for_matching_event(self):
        """Hooks registered for event A should not fire on event B."""
        called = []
        r = HookRegistry()
        r.register("intent", lambda e: called.append(e))

        r.fire("tool_exec", name="calc")

        assert called == []

    def test_custom_hook_exception_does_not_others(self):
        """One failing hook should not prevent others from running."""
        order = []

        def bad_hook(e):
            order.append("bad")
            raise ValueError("boom")

        def good_hook(e):
            order.append("good")

        r = HookRegistry()
        r.register("test", bad_hook)
        r.register("test", good_hook)

        r.fire("test")

        assert order == ["bad", "good"]

    def test_fire_with_bound_log_and_custom_hook(self):
        """Both log.step() and custom hook should be called."""
        class FakeLog:
            def __init__(self):
                self.calls = []

            def step(self, module, **kwargs):
                self.calls.append(module)

        log = FakeLog()
        hook_calls = []
        r = HookRegistry()
        r.bind_log(log)
        r.register("intent", lambda e: hook_calls.append(e))

        r.fire("intent", result="chat")

        assert log.calls == ["intent"]
        assert len(hook_calls) == 1
