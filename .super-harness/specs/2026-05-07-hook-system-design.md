# Hook 系统 + FlowLog 重构设计

**Date:** 2026-05-07
**Status:** Draft

## Goal

建立独立的 Hook 事件系统，并将 FlowLog 重构为 Hook 的监听者，解除核心模块与日志系统的直接耦合，为未来扩展（权限检查、通知、审计）打下地基。

## Architecture

采用观察者模式：核心模块通过 `HookRegistry.fire()` 触发事件，FlowLog 通过 `bind_log()` 成为默认监听者。Hook 系统作为独立顶层模块 `hooks/`，与 `log/`、`infra/` 平级。

```
核心模块 ---(fire event)---> HookRegistry ---(自动转发)---> FlowLog.step()
                               |
                               +---> 其他自定义 hook（未来扩展）
```

## Components

### 1. `hooks/registry.py` — HookRegistry + HookEvent

- `HookEvent`: dataclass，包含 `name`（事件名）和 `data`（dict 数据）
- `HookRegistry`:
  - `bind_log(log)`: 绑定 FlowLog 实例，所有事件自动转发到 `log.step()`
  - `register(event, hook)`: 注册自定义 hook 函数
  - `fire(event, **data)`: 同步触发事件，先转发 FlowLog，再调用自定义 hook
- 性能：无自定义 hook 时开销 ≈ 100ns/次，对比 LLM 调用 (500ms+) 可忽略

### 2. `log/flow.py` — FlowLog（不变）

- 零改动。仍然通过 `step(module, **kwargs)` 接收事件
- `set_model()` / `set_error()` 保持直接调用，不走 Hook
- `finish()` / `to_text()` 输出格式不变

### 3. `cli/app.py` — 初始化与绑定

- 创建 `HookRegistry`，调用 `hooks.bind_log(log)`
- `classify_intent()` 传 `hooks=hooks` 替代 `log=log`
- `OrchestratorContext` 传 `hooks=hooks` 替代 `log=log`
- `set_model()` / `set_error()` / `flush_log()` 仍然直接操作 `log`

### 4. `router/intent.py` — 参数替换

- 函数签名 `log=None` → `hooks=None`
- `log.step(...)` → `hooks.fire(...)`

### 5. `orchestrator/engine.py` — Context 字段重命名

- `OrchestratorContext.log` → `OrchestratorContext.hooks`

### 6. `orchestrator/state_machine.py` + `langgraph_engine.py` — 调用替换

- `context.log.step(...)` → `context.hooks.fire(...)`

## Data Flow

一次完整的 `_process()` 调用中，事件流经路径：

```
1. cli/app.py:  hooks.fire("memory", msgs=..., window=..., chars=..., context_window=...)
2. router/intent.py:  hooks.fire("intent", result=..., via=..., model=..., ms=...)
3. cli/app.py:  hooks.fire("complexity", result=...)
4. cli/app.py:  hooks.fire("router", model=..., reason=...)
5. orchestrator/:  hooks.fire("orch_plan", iter=..., tools=..., ms=...)
6. orchestrator/:  hooks.fire("tool_exec", name=..., result=..., ms=...)
7. cli/app.py:  hooks.fire("persist", saved=...)
```

每个 `fire()` 内部：
1. `self._log.step(event, **data)` — 转发到 FlowLog（和之前直接调用完全一致）
2. 遍历 `self._hooks[event]`，调用每个自定义 hook

## Event Name Reference

| 事件名 | 触发位置 | 数据字段 |
|--------|---------|---------|
| `memory` | cli/app.py | `msgs`, `window`, `chars`, `context_window` |
| `intent` | router/intent.py | `result`, `via`, `model`, `response`, `ms`, `prompt_msgs`, `prompt` |
| `complexity` | cli/app.py | `result` |
| `router` | cli/app.py | `model`, `reason` |
| `orch_plan` | orchestrator/ | `iter`, `tools`, `ms`, `msg_count`, `prompt`, `response` |
| `tool_exec` | orchestrator/ | `name`, `args`, `result`, `ms` |
| `persist` | cli/app.py | `saved` |

## Error Handling

- `fire()` 在 `log=None` 时安全跳过转发（`bind_log` 未调用时不报错）
- `fire()` 中单个自定义 hook 异常不影响其他 hook 和 FlowLog 转发
- `set_model()` / `set_error()` 不走 Hook，异常直接向上传播

## Testing Strategy

### 新增 `tests/test_hooks.py`

- HookRegistry 初始化（无 hook、无 log）
- `bind_log()` 后 `fire()` 正确转发到 `FlowLog.step()`
- `register()` 自定义 hook 在 `fire()` 时被调用
- 多个 hook 按注册顺序执行
- `fire()` 无绑定 log 时不报错
- 自定义 hook 中的异常不影响其他 hook

### 修改 `tests/test_flow_log.py`

- 通过 OrchestratorContext 传递 log 的测试 → 改为传递 hooks
- 直接测试 FlowLog 的测试 → 不改

### 不变量验证

- 所有现有测试通过
- `/log` 命令输出对比 diff 为零差异

## File Change Summary

| 文件 | 改动 | 量 |
|------|------|-----|
| `hooks/__init__.py` | **新增** | ~3行 |
| `hooks/registry.py` | **新增** | ~50行 |
| `cli/app.py` | 修改 | ~10行 |
| `router/intent.py` | 修改 | ~5行 |
| `orchestrator/engine.py` | 修改 | ~3行 |
| `orchestrator/state_machine.py` | 修改 | ~5行 |
| `orchestrator/langgraph_engine.py` | 修改 | ~5行 |
| `tests/test_hooks.py` | **新增** | ~80行 |
| `tests/test_flow_log.py` | 修改 | 适配 hooks 参数 |
| `log/flow.py` | **不变** | 0 |
| `log/writer.py` | **不变** | 0 |

## Out of Scope

- Hook 的 async 版本（当前不需要）
- 权限检查 hook（未来扩展）
- 外部通知 hook（未来扩展）
- `hooks/` 目录下的子模块拆分（当前只有 registry.py）
- FlowLog 的 `set_model()` / `set_error()` 改为 Hook 事件（语义不适合）
