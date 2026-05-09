# Spinner 空白修复 + Onboarding 深度改进 设计

**Date:** 2026-05-08
**Status:** Draft

## Goal

消除工具调用前的 Spinner 空白期，并提升 Onboarding 问答深度以生成更丰富的 user.md 和 soul.md。

## Architecture

两个独立改进，无代码依赖：
1. **Spinner fix**: StreamRenderer 内嵌 activity indicator，在文本流结束后 0.8s 自动显示 Braille 动画
2. **Onboarding depth**: 重写 `_ONBOARDING_TEMPLATE`，引导 Agent 进行多阶段自然对话后再创建文件

---

## Component 1: StreamRenderer Embedded Activity Indicator

### Problem

当 LLM 完成文本生成、开始生成 tool_call JSON 参数时（1-3 秒），终端没有任何视觉反馈：
- StageIndicator 在第一个 text_delta 时已被 finish
- StreamRenderer 没有新内容可渲染
- 用户看到空白

根因：OpenAI/Anthropic provider 在 HTTP stream 关闭后才 yield tool_call 事件。

### Solution

在 StreamRenderer 中添加 activity indicator：当 `push_delta()` 超过 0.8 秒未被调用且 `pending` 非空时，在 Live 显示区域底部显示 Braille 动画。

### Changes

#### `cli/stream_renderer.py`

新增字段：
- `_last_delta_time: float` — 最后一次 `push_delta()` 的时间戳
- `_indicator_label: str` — indicator 文本，默认 `"Waiting for tool call..."`

新增方法：
- `_build_display() -> Group` — 构建完整显示内容：
  - 已渲染的 Markdown 内容
  - 如果 `pending` 非空且 `time.time() - _last_delta_time > 0.8`，追加 Braille spinner
  - Braille frame 通过 `int(time.time() * 10) % 10` 计算，无需后台线程

修改方法：
- `push_delta()` — 更新 `_last_delta_time`
- `_update_display()` — 调用 `_build_display()` 替代直接 `Markdown(self.rendered)`
- `start()` — 初始化 `_last_delta_time = time.time()`

#### `cli/stage_indicator.py`

新增字段：
- `_finished: bool` — 跟踪是否已 finish，防止重复调用

修改方法：
- `finish()` — 检查 `_finished` 标志
- `update()` — 检查 `_finished` 标志
- 新增 `stop_silent()` — 静默停止 spinner（不打印 "Done"），设置 `_finished = True`

#### `cli/app.py` — `_process_streaming()`

修改 text_delta 处理：
```
第一个 text_delta 到达时：
  indicator.stop_silent()     # 替代 indicator.finish()
  创建 StreamRenderer        # 不变
```

其余逻辑不变：tool_call 时 `renderer.flush()`，流结束时 `indicator.finish()`。

### User Experience

**改进前：**
```
  ⏺ 好了，让我把这些信息记下来——
                                          ← 空白 1-3 秒
╭─ ✏️ file_write ────────────────────────╮
```

**改进后：**
```
  ⏺ 好了，让我把这些信息记下来——
  ⠋ Waiting for tool call...              ← activity indicator 自动出现
╭─ ✏️ file_write ────────────────────────╮
```

---

## Component 2: Onboarding Q&A Depth

### Problem

当前 `_ONBOARDING_TEMPLATE` 只问 3 个问题（称呼、角色、技术背景），Agent 在 2 轮对话后就急着创建文件，导致：
- user.md 只有称呼和角色
- soul.md 是通用模板，无个性化

### Solution

重写 `_ONBOARDING_TEMPLATE`，采用三阶段对话流程：

**Phase 1: 互相认识（自然聊天）**
- 一次问 1-2 个问题，不要审讯式提问
- 用户维度：称呼、角色/行业、年龄段（范围即可）、性别、技术栈、沟通风格偏好
- Agent 对每个回答自然反应后再问下一个
- 语言跟随用户

**Phase 2: 性格协商**
- Agent 根据用户 vibe 提议自己的性格
- 问用户：语气（直接/温暖/幽默/毒舌）、关系定位（同事/朋友/助手）、具体偏好
- 用户确认或调整

**Phase 3: 创建文件（至少 4 轮用户回复后）**
- 使用 file_write 创建 user.md 和 soul.md
- 自然过渡到正常对话

### Changes

#### `memory/strategy.py` — `_ONBOARDING_TEMPLATE`

完全重写，内容包括：
- 三阶段流程说明
- 每阶段的具体问题列表（中英双语）
- 硬约束：`"至少 4 轮用户回复后才能创建文件"`
- 输出结构指引：user.md 和 soul.md 的预期 section 结构
- OpenClaw 哲学："了解一个人，不是建档案"

#### `memory/strategy.py` — `_MEMORY_MGMT_TEMPLATE`

小改动：
- 扩展 "When to update soul.md" 部分
- 添加性格反馈信号词：`"你太正式了"`, `"别那么客气"`, `"说话直接点"`, `"太啰嗦了"`

### Expected Output Quality

**user.md 预期结构：**
```markdown
# User - {name}
## 基本信息
- 称呼 / 性别 / 年龄段 / 角色 / 行业
## 技术背景
- 主要技术栈 / 技术水平 / 工作内容
## 沟通偏好
- 语言 / 风格 / 回复长度
## 性格特点
## 备注
```

**soul.md 预期结构：**
```markdown
# Soul - {agent_name}
## 核心性格
## 沟通风格
- 语言 / 语气 / 人称 / 回复长度 / 口头禅
## 专长领域
## 行为准则
## 与用户的关系定位
```

---

## Error Handling

### Spinner fix
- `_build_display()` 中的 Braille frame 计算使用 `time.time()`，不依赖外部状态，不会抛异常
- `stop_silent()` 是幂等的，多次调用安全

### Onboarding
- 用户拒绝回答某问题 → Agent 跳过，不追问
- 用户直接要求创建文件（跳过问答）→ Agent 应遵守但提醒"我可以了解更多以提供更好的个性化"
- 用户用英文 → 所有问题用英文

## Testing Strategy

### Spinner fix
- 手动测试：发送会产生 tool_call 的 prompt，观察文本流结束后是否有 activity indicator
- 验证 indicator 在 push_delta 恢复后立即消失
- 验证 flush() 后 indicator 不残留

### Onboarding
- 删除 memory/data/soul.md 和 user.md，启动新会话
- 验证 Agent 至少问 4 个问题才创建文件
- 验证生成的 user.md 和 soul.md 包含所有预期 section
- 验证中文用户收到中文问题

## Out of Scope

- Spinner 与 StreamRenderer 的视觉合并（两个 Live display 共存方案）— 不需要，当前方案已解决
- 代码层面的 template schema 验证 — prompt 约束足够
- user.md/soul.md 的自动 section 检查 — 过度工程化
- 其他 improvement_report 中的改进项

## File Change Summary

| File | Change | Lines |
|------|--------|-------|
| `cli/stream_renderer.py` | 新增 `_last_delta_time`, `_indicator_label`, `_build_display()` | ~25 |
| `cli/stage_indicator.py` | 新增 `_finished` 字段, `stop_silent()` 方法 | ~10 |
| `cli/app.py` | `indicator.finish()` → `indicator.stop_silent()` on first text_delta | ~3 |
| `memory/strategy.py` | 重写 `_ONBOARDING_TEMPLATE`, 小改 `_MEMORY_MGMT_TEMPLATE` | ~80 |
