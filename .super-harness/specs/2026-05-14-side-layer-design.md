# Side 层改造设计

**Date:** 2026-05-14
**Status:** Draft

## Goal

将 Brix 的 intent 分类层重构为 side 辅助层，参考 Claude Code 的 Haiku "杂事"架构，用小模型处理主对话之外的辅助任务。

## Architecture

删除 `router/` 层（intent 分类 + 复杂度评估 + 模型路由），新建 `side/` 层（SideTaskManager + 7 个独立可插拔的 side tasks）。主模型直接从 config 读取，不再动态路由。Side 层完全可选，失败不影响主流程。

**数据流**：
```
用户输入 → [memory 构建 system prompt] → [side: history_search 触发检测] → orchestrator.run_stream() → [side: tool_summary, pref_detection 后处理]
```

## Components

### 1. Side 层骨架

| 文件 | 职责 |
|------|------|
| `side/__init__.py` | 包入口，导出 SideTaskManager |
| `side/base.py` | SideTask 抽象基类 + SideTaskContext 数据类 |
| `side/manager.py` | SideTaskManager — configure/register/run_task/fire_and_forget |
| `side/tasks/__init__.py` | ALL_TASKS 列表，注册所有 task 实例 |

### 2. 七个 Side Tasks

| Task | 触发方式 | 职责 |
|------|---------|------|
| `session_title` | 会话结束时 | 生成 3-7 词会话标题 |
| `tool_summary` | tool_result 事件后 (fire-and-forget) | 生成工具调用摘要标签 |
| `pref_detection` | 每 N 轮用户消息 (fire-and-forget) | 检测用户偏好/纠正，写入 memory |
| `history_search` | 关键词触发（之前/上次/记得等） | 语义搜索历史会话，注入上下文 |
| `voice_cleanup` | 语音输入时 | 清理口语化填充词、修正识别错误 |
| `context_compress` | 消息数超过阈值时 | 压缩旧消息为摘要 |
| `session_summary` | 空闲超过阈值后回来时 | 生成离开期间的会话摘要 |

### 3. Config 改造

routing 简化（删除 chat_model、intent_model），新增 side 配置块（总开关 + model + 每个 task 的独立开关和参数）。

### 4. CLI 集成

- `BrixCLI.__init__()` 初始化 SideTaskManager，注册所有 tasks
- `_process_streaming()` 删除 Intent/Complexity/Route 阶段，接入 side 层
- 语音清理改用 side 层的 voice_cleanup task

### 5. /model 命令改造

支持查看当前模型、切换模型（运行时）、持久化到 settings.local.yaml。

## Data Flow

1. 用户输入到达
2. Memory 构建 system prompt（不变）
3. Side 层检测 history_search 触发关键词，如有匹配则搜索并注入上下文
4. 直接使用 config 中的 default_model 调用 orchestrator
5. orchestrator 流式执行，tool_result 事件后 fire-and-forget tool_summary
6. 持久化后，按间隔触发 pref_detection
7. 用户消息计数递增

## Error Handling

所有 side task 遵循"静默失败"原则：
- 任何异常（LLM 超时、JSON 解析失败、网络错误）→ 返回 None
- logger.warning 记录错误
- 主流程完全不受 side task 失败影响

## Testing Strategy

- **单元测试**：每个 side task 独立测试，mock LLMClient.chat() 返回预设响应
- **集成测试**：验证 SideTaskManager 与 CLI 的集成（tool_summary 触发、pref_detection 间隔、history_search 关键词）
- **回归测试**：brix 启动、对话、/model 命令、语音模式正常

## Out of Scope

- 不改变 orchestrator 内部逻辑
- 不改变 memory 层实现
- 不改变 capability/tools 层（除 /model 命令外）
- 不添加新的 LLM provider

## 删除清单

- `router/intent.py`、`router/complexity.py`、`router/model_router.py`、`router/__init__.py`
- `tests/test_router.py`

## 实施策略

采用直接替换方案（方案 B），按 6 个阶段顺序执行：
1. Side 层骨架
2. Config 改造
3. 实现 7 个 Side Tasks
4. CLI 集成
5. /model 命令改造
6. 清理（删除 router/）
