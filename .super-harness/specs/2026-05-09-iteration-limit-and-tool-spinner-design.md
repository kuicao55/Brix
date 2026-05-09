# max_iterations 调整 + 工具执行 Spinner 设计

**Date:** 2026-05-09
**Status:** Draft

## Goal

解决两个体验问题：(1) 复杂任务因 max_iterations=5 被截断；(2) 工具执行期间无动态反馈。

## Architecture

两个独立的小改动，互不依赖：
- Feature 14: 调整 `StateMachineOrchestrator` 的迭代上限默认值
- Feature 15: 在 `ToolDisplay` 中嵌入 `Spinner`，生命周期与工具执行绑定

## Components

### Feature 14: max_iterations 默认值调整

**文件**: `orchestrator/state_machine.py`

将 `max_iterations` 默认值从 `5` 改为 `100`。参考 Claude Code（无上限）和 Claw-code（`usize::MAX`），100 是安全兜底值，防止无限循环，实际正常任务不会触及。

同时改进 fallback 消息，加入迭代数信息方便 debug：
- `run()`: `"I was unable to complete the request within {self.max_iterations} steps."`
- `run_stream()`: 同上

### Feature 15: 工具执行 Spinner

**文件**: `cli/tool_display.py`, `cli/app.py`

在 `ToolDisplay` 中嵌入 `Spinner`（复用 `cli/spinner.py` 的已有实现），生命周期与工具执行绑定：

1. `show_tool_start()`: 打印静态面板后，启动 `Spinner(console, label="Calling tools...")`
2. `show_tool_result()`: 停止 `_active_spinner`，打印结果行
3. `cleanup()`: 新增安全网方法，异常路径清理 spinner

`Spinner` 使用 `Live(transient=True)`，停止后自动消失，不干扰后续输出。

## Data Flow

### Feature 14
```
用户请求 → Orchestrator.run() → for iter in range(1, 101):
                                    plan → execute → ...
                                 → (若耗尽) fallback with iteration count
```

### Feature 15
```
tool_call event  → ToolDisplay.show_tool_start()
                   ├── console.print(panel)        # 静态面板
                   └── Spinner.start()             # Braille 动画开始
                       ↓
                   [工具执行中... Spinner 持续旋转]
                       ↓
tool_result event → ToolDisplay.show_tool_result()
                   ├── Spinner.stop()              # 动画停止，Live 消失
                   └── console.print(result)       # 结果行
```

## Error Handling

- **Feature 14**: 无额外错误处理需求。100 次迭代足够覆盖所有正常场景。
- **Feature 15**: 异常路径处理 — 在 `cli/app.py` 的 `_process_streaming()` 的 `finally` 块中调用 `tool_display.cleanup()`，确保工具执行抛异常时 spinner 不会泄漏。

## Testing Strategy

- **Feature 14**: 修改现有测试中对 `max_iterations` 默认值的断言（如有），验证 fallback 消息包含迭代数
- **Feature 15**: 新增测试验证 `show_tool_start()` 启动 spinner，`show_tool_result()` 停止 spinner，`cleanup()` 在无活跃 spinner 时安全调用

## Out of Scope

- 不改变迭代计数逻辑（仍按 LLM plan 调用计数）
- 不引入可配置的 max_iterations（保持为构造函数参数）
- 不改变 ToolDisplay 的静态面板样式
- 不改变 Spinner 类本身（复用已有实现）
