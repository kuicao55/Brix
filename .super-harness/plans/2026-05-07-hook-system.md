# Hook 系统 + FlowLog 重构 Implementation Plan

> **Harness note:** This plan is executed via `harness-execution` using the Orchestrator / Executor / Reviewer architecture. Each task goes through Executor (TDD implementation) → Spec Reviewer (compliance check) → Code Quality Reviewer (adversarial review). Only Code Quality Review PASS closes a task.

**Goal:** 建立独立的 Hook 事件系统，并将 FlowLog 重构为 Hook 的监听者，解除核心模块与日志系统的直接耦合。

**Milestone ref:** milestone-3 from claude-progress.json

**Architecture:** 观察者模式。核心模块通过 `HookRegistry.fire()` 触发事件，FlowLog 通过 `bind_log()` 成为默认监听者。Hook 系统作为独立顶层模块 `hooks/`，与 `log/`、`infra/` 平级。

**Tech Stack:** Python 3.11+, pytest, dataclasses

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `hooks/__init__.py` | Create | Re-export HookRegistry, HookEvent |
| `hooks/registry.py` | Create | HookRegistry + HookEvent 核心实现 (~50行) |
| `cli/app.py` | Modify | 初始化 HookRegistry，绑定 FlowLog，替换 log 传递为 hooks |
| `router/intent.py` | Modify | 参数 log → hooks，log.step → hooks.fire |
| `orchestrator/engine.py` | Modify | OrchestratorContext.log → hooks |
| `orchestrator/state_machine.py` | Modify | context.log.step → context.hooks.fire |
| `orchestrator/langgraph_engine.py` | Modify | context.log.step → context.hooks.fire |
| `tests/test_hooks.py` | Create | HookRegistry 测试 (~80行) |
| `tests/test_flow_log.py` | Modify | 适配 hooks 参数 |

---

### Task 1: hooks/registry.py — HookRegistry + HookEvent

**Files:**

- Create: `hooks/registry.py`
- Create: `hooks/__init__.py`
- Test: `tests/test_hooks.py`

**TDD_EVIDENCE:** Step 2 (RED): `pytest tests/test_hooks.py` should FAIL with ModuleNotFoundError or AssertionError. Step 4 (GREEN): same command should PASS with all tests green.

- [x] **Step 1: Write the failing test**

```python
# tests/test_hooks.py
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /Users/kuicao/Applications/Brix && python -m pytest tests/test_hooks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hooks'`

- [x] **Step 3: Write minimal implementation**

```python
# hooks/registry.py
"""Lightweight event registry for the Hook system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class HookEvent:
    """Hook event carrier."""
    name: str
    data: dict[str, Any] = field(default_factory=dict)


class HookRegistry:
    """Lightweight event registration and dispatch center."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[Callable[[HookEvent], None]]] = {}
        self._log: Any = None

    def bind_log(self, log: Any) -> None:
        """Bind a FlowLog instance. All events auto-forward to log.step()."""
        self._log = log

    def register(self, event: str, hook: Callable[[HookEvent], None]) -> None:
        """Register a custom hook for an event."""
        self._hooks.setdefault(event, []).append(hook)

    def fire(self, event: str, **data: Any) -> None:
        """
        Fire an event (synchronous).
        1. Forward to FlowLog.step() if bound.
        2. Call all registered custom hooks.
        """
        if self._log is not None:
            self._log.step(event, **data)

        hook_event = HookEvent(name=event, data=data)
        for hook in self._hooks.get(event, []):
            try:
                hook(hook_event)
            except Exception:
                pass  # one failing hook does not affect others
```

```python
# hooks/__init__.py
"""Hook event registry."""

from hooks.registry import HookEvent, HookRegistry

__all__ = ["HookEvent", "HookRegistry"]
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd /Users/kuicao/Applications/Brix && python -m pytest tests/test_hooks.py -v`
Expected: PASS — all 10 tests green

- [x] **Step 5: Commit**

```bash
git add hooks/__init__.py hooks/registry.py tests/test_hooks.py
git commit -m "feat: add HookRegistry event system with tests"
```

---

### Task 2: Integration — Refactor modules to use hooks.fire()

**Files:**

- Modify: `cli/app.py`
- Modify: `router/intent.py`
- Modify: `orchestrator/engine.py`
- Modify: `orchestrator/state_machine.py`
- Modify: `orchestrator/langgraph_engine.py`

**TDD_EVIDENCE:** `pytest tests/` — all existing tests should PASS with zero failures. Behavior is unchanged; only the call path changed (hooks.fire instead of log.step).

- [x] **Step 1: Run existing tests to establish baseline**

Run: `cd /Users/kuicao/Applications/Brix && python -m pytest tests/ -v`
Expected: all tests PASS (baseline)

- [x] **Step 2: Modify orchestrator/engine.py — rename Context field**

```python
# orchestrator/engine.py
# Change:
#     log: Any = None  # FlowLog
# To:
#     hooks: Any = None  # HookRegistry
```

- [x] **Step 3: Modify orchestrator/state_machine.py — log.step → hooks.fire**

```python
# orchestrator/state_machine.py
# In _plan method, change:
#     if context.log:
#         context.log.step("orch_plan", ...)
# To:
#     if context.hooks:
#         context.hooks.fire("orch_plan", ...)

# In _execute method, change:
#     if context.log:
#         context.log.step("tool_exec", ...)
# To:
#     if context.hooks:
#         context.hooks.fire("tool_exec", ...)
```

- [x] **Step 4: Modify orchestrator/langgraph_engine.py — same pattern**

```python
# orchestrator/langgraph_engine.py
# In _plan_node, change:
#     if context.log:
#         context.log.step("orch_plan", ...)
# To:
#     if context.hooks:
#         context.hooks.fire("orch_plan", ...)

# In _execute_node, change:
#     if context.log:
#         context.log.step("tool_exec", ...)
# To:
#     if context.hooks:
#         context.hooks.fire("tool_exec", ...)
```

- [x] **Step 5: Modify router/intent.py — log → hooks**

```python
# router/intent.py
# Change function signature:
#     async def classify_intent(user_input, history, llm_client, model, log=None):
# To:
#     async def classify_intent(user_input, history, llm_client, model, hooks=None):

# Change all log.step(...) calls to hooks.fire(...)
# Change all `if log:` guards to `if hooks:`
```

- [x] **Step 6: Modify cli/app.py — initialize hooks, bind log, replace log passing**

```python
# cli/app.py
# Add import:
#     from hooks.registry import HookRegistry

# In _process(), after creating log:
#     log = FlowLog(user_input)
#     hooks = HookRegistry()
#     hooks.bind_log(log)

# Change classify_intent call:
#     intent = await classify_intent(..., hooks=hooks)
#     # was: log=log

# Change log.step("memory", ...) to hooks.fire("memory", ...)
# Change log.step("complexity", ...) to hooks.fire("complexity", ...)
# Change log.step("router", ...) to hooks.fire("router", ...)
# Change log.step("persist", ...) to hooks.fire("persist", ...)

# Change OrchestratorContext creation:
#     context = OrchestratorContext(..., hooks=hooks)
#     # was: log=log

# Keep unchanged:
#     log.set_model(model)
#     log.set_error(str(exc))
#     log.set_error(response)
#     flush_log(log)
```

- [x] **Step 7: Run all tests to verify no regressions**

Run: `cd /Users/kuicao/Applications/Brix && python -m pytest tests/ -v`
Expected: all tests PASS — behavior unchanged

- [x] **Step 8: Commit**

```bash
git add cli/app.py router/intent.py orchestrator/engine.py orchestrator/state_machine.py orchestrator/langgraph_engine.py
git commit -m "refactor: replace direct FlowLog calls with HookRegistry.fire()"
```

---

### Task 3: Update tests/test_flow_log.py — adapt to hooks

**Files:**

- Modify: `tests/test_flow_log.py`
- Modify: `tests/test_orchestrator.py` (if it references context.log)
- Modify: `tests/test_router.py` (if it references log= parameter)
- Modify: `tests/test_langgraph.py` (if it references context.log)
- Modify: `tests/test_cli.py` (if it references log)

**TDD_EVIDENCE:** `pytest tests/test_flow_log.py tests/test_orchestrator.py tests/test_router.py tests/test_langgraph.py tests/test_cli.py -v` — all PASS.

- [x] **Step 1: Find all test references to old log pattern**

Run: `cd /Users/kuicao/Applications/Brix && grep -rn "context\.log\|log=log\|log=.*FlowLog" tests/`
Expected: list of lines that need updating

- [x] **Step 2: Update test files**

For each test file:
- `context.log = ...` → `context.hooks = HookRegistry()` (with bind_log if needed)
- `log=log` parameter in function calls → `hooks=hooks`
- Direct FlowLog tests → **no change**

```python
# Pattern for tests that create OrchestratorContext:
# Before:
#     ctx = OrchestratorContext(..., log=some_log)
# After:
#     from hooks.registry import HookRegistry
#     hooks = HookRegistry()
#     hooks.bind_log(some_log)
#     ctx = OrchestratorContext(..., hooks=hooks)
```

- [x] **Step 3: Run updated tests**

Run: `cd /Users/kuicao/Applications/Brix && python -m pytest tests/ -v`
Expected: all tests PASS

- [x] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: adapt tests to use HookRegistry instead of direct FlowLog"
```

---

### Task 4: End-to-end verification

**Files:**

- No new files — verification only

**TDD_EVIDENCE:** `pytest tests/ -v` — all tests PASS. Manual `/log` command output matches previous format exactly.

- [x] **Step 1: Run full test suite**

Run: `cd /Users/kuicao/Applications/Brix && python -m pytest tests/ -v --tb=short`
Expected: all tests PASS

- [x] **Step 2: Verify /log output format preserved**

Run: `cd /Users/kuicao/Applications/Brix && python -c "
from log.flow import FlowLog
from hooks.registry import HookRegistry

log = FlowLog('test input')
hooks = HookRegistry()
hooks.bind_log(log)

# Simulate the full pipeline
hooks.fire('memory', msgs=5, window=3, chars=100, context_window=[])
hooks.fire('intent', result='chat', via='llm', model='gpt-4', ms=100, prompt_msgs=2, prompt='test')
hooks.fire('complexity', result='low')
hooks.fire('router', model='gpt-4', reason='chat->low')
hooks.fire('orch_plan', iter=1, tools=['calc'], ms=200, msg_count=5, prompt='test', response='ok')
hooks.fire('tool_exec', name='calc', args={'expr': '1+1'}, result='2', ms=50)
hooks.fire('persist', saved=1)
log.set_model('gpt-4')

print(log.to_text())
print('---')
print('finish() keys:', sorted(log.finish().keys()))
"
Expected: output matches the same format as before refactoring (memory -> intent -> complexity -> router -> plan -> exec -> persist chain)

- [x] **Step 3: Verify no old log.step patterns remain in source**

Run: `cd /Users/kuicao/Applications/Brix && grep -rn "context\.log\b\|\.log\.step" cli/ router/ orchestrator/ --include="*.py"`
Expected: no matches (all migrated to hooks.fire)

- [x] **Step 4: Final commit with all files**

```bash
git add -A
git commit -m "feat: Hook system with FlowLog as listener (milestone-3 complete)"
```
