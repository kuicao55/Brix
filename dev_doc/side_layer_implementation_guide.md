# Brix Side 层改造实施指南

> **目的**：将 Brix 的 intent 分类层重构为 side 辅助层，参考 Claude Code 的 Haiku "杂事"架构。
> **状态**：待实施
> **预计跨度**：多个 session，按阶段推进

---

## 目录

1. [背景与动机](#1-背景与动机)
2. [当前架构（AS-IS）](#2-当前架构as-is)
3. [目标架构（TO-BE）](#3-目标架构to-be)
4. [Claude Code 参考实现](#4-claude-code-参考实现)
5. [Side 层详细设计](#5-side-层详细设计)
6. [Config 改造](#6-config-改造)
7. [Router 层处理](#7-router-层处理)
8. [CLI 层改造](#8-cli-层改造)
9. [/model 命令改造](#9-model-命令改造)
10. [实施阶段规划](#10-实施阶段规划)
11. [测试策略](#11-测试策略)
12. [附录：完整代码参考](#12-附录完整代码参考)

---

## 1. 背景与动机

### 问题

Brix 当前的 intent 层（`router/` 包）每条用户消息都会调用一次 LLM 进行意图分类，然后根据分类结果选择不同模型。这导致：

- **每条消息多一次 LLM 延迟**（即使是"你好"也要先分类）
- **7 个 intent 边界模糊**，分类容易出错
- **用户体感被不断切换模型**，对话不连贯

### 解决方案

参考 Claude Code 的做法：**小模型不做决策，做杂活**。将 intent 层从"分类器"转变为"辅助任务执行层"（side layer），用小模型处理主对话之外的辅助任务。

### 核心原则

1. **Side 层完全可选** — 没有它 agent 也能正常运行
2. **每个能力独立可插拔** — config 中单独开关
3. **不阻塞主流程** — side 任务尽量异步/fire-and-forget
4. **主模型直接指定** — 不再动态路由

---

## 2. 当前架构（AS-IS）

### 数据流

```
用户输入
  → classify_intent()        [router/intent.py, LLM 调用 ali/qwen3.6-flash]
  → evaluate_complexity()     [router/complexity.py, 纯规则]
  → select_model()            [router/model_router.py, intent+complexity → model]
  → orchestrator.run_stream() [用选中的模型执行]
```

### 需要删除/替换的文件

| 文件 | 行数 | 处理方式 |
|------|------|---------|
| `router/intent.py` | 123 | **删除** — 被 side 层替代 |
| `router/complexity.py` | 33 | **删除** — 不再需要 |
| `router/model_router.py` | 64 | **删除** — 主模型直接从 config 读取 |
| `router/__init__.py` | 2 | **删除** — 包不再需要 |

### 需要修改的文件

| 文件 | 修改内容 |
|------|---------|
| `config/settings.yaml` | 简化 routing，新增 side 配置块 |
| `config/model_registry.py` | 保留，微调 |
| `config/loader.py` | 保留不动 |
| `cli/app.py` | 移除 intent/complexity/route 阶段，集成 side 层 |
| `capability/command/builtin/info.py` | 改造 ModelCommand 支持切换 |
| `capability/basics/commands.py` | 更新静态命令列表 |
| `tests/test_router.py` | **删除** — 测试的是被删除的模块 |

### 当前 settings.yaml 的 routing 部分

```yaml
routing:
  default_model: "minimax/MiniMax-M2.7"
  fallback_model: "minimax/MiniMax-M2.7"
  chat_model: "zenmux-openai/deepseek/deepseek-v4-flash"    # 将删除
  intent_model: "ali/qwen3.6-flash"                          # 将删除
```

### 当前 cli/app.py 的处理流程（关键行号）

- **行 324-335**：Intent 阶段 — `classify_intent()` 调用
- **行 337-346**：Complexity + Route 阶段 — `evaluate_complexity()` + `select_model()`
- **行 348-354**：构建 OrchestratorContext，使用选中的 model
- **行 360**：Planning 阶段 — `indicator.update("Planning", model.split("/")[-1])`

### 当前 ModelCommand（capability/command/builtin/info.py:51-68）

```python
class ModelCommand(Command):
    """查看当前默认模型。"""
    def __init__(self, config: dict) -> None:
        self._config = config

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="model",
            description="查看当前默认模型",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        default_model = self._config.get("routing", {}).get("default_model", "unknown")
        print(f"Current model: {default_model}")
        return CommandResult(type=CommandResultType.NONE)
```

---

## 3. 目标架构（TO-BE）

### 数据流

```
用户输入
  → [memory 构建 system prompt]        # 不变
  → [side tasks 触发检测]              # 新增：检查是否有 side task 需要执行
  → orchestrator.run_stream()          # 直接使用 config 中指定的主模型
  → [side tasks 后处理]                # 新增：工具摘要、偏好检测等
```

### 目录结构

```
side/
  __init__.py              # 包入口，导出 SideTaskManager
  base.py                  # SideTask 抽象基类
  manager.py               # SideTaskManager — 加载、调度、执行
  tasks/
    __init__.py
    session_title.py       # 会话标题生成
    tool_summary.py        # 工具调用结果摘要
    pref_detection.py      # 用户偏好/习惯检测
    history_search.py      # 历史记忆语义搜索
    voice_cleanup.py       # 语音输入文本清理
    context_compress.py    # 长对话上下文压缩
    session_summary.py     # 离开后回来的会话摘要
```

### Config 结构（新增 side 块）

```yaml
side:
  enabled: true                          # 总开关
  model: "ali/qwen3.6-flash"             # side 任务专用小模型
  tasks:
    session_title:
      enabled: true
    tool_summary:
      enabled: true
    pref_detection:
      enabled: true
      interval: 5                        # 每 N 轮用户消息检测一次
    history_search:
      enabled: true
      top_k: 3                           # 返回最相关的 N 条历史
      trigger_keywords:                  # 触发关键词
        - "之前"
        - "上次"
        - "记得"
        - "曾经"
        - "以前"
        - "previously"
        - "last time"
        - "remember"
    voice_cleanup:
      enabled: true
    context_compress:
      enabled: true
      message_threshold: 50              # 消息数超过此阈值时触发压缩
    session_summary:
      enabled: true
      idle_threshold_minutes: 5          # 空闲超过此时间后触发
```

---

## 4. Claude Code 参考实现

### 4.1 模型选择 — `getSmallFastModel()`

**文件**: `claude-code/src/utils/model/model.ts` (行 42-56)

```typescript
export function getSmallFastModel(): ModelName {
  const provider = getAPIProvider()
  if (provider === 'openai' && isChatGPTAuthMode()) {
    return process.env.OPENAI_SMALL_FAST_MODEL ?? CHATGPT_CODEX_FAST_MODEL
  }
  if (provider === 'openai' && process.env.OPENAI_SMALL_FAST_MODEL) {
    return process.env.OPENAI_SMALL_FAST_MODEL
  }
  if (provider === 'gemini' && process.env.GEMINI_SMALL_FAST_MODEL) {
    return process.env.GEMINI_SMALL_FAST_MODEL
  }
  return process.env.ANTHROPIC_SMALL_FAST_MODEL || getDefaultHaikuModel()
}
```

**Brix 对应实现**：不需要单独的函数，直接从 `config["side"]["model"]` 读取即可。

### 4.2 查询封装 — `queryHaiku()`

**文件**: `claude-code/src/services/api/claude.ts` (行 3421-3473)

```typescript
export async function queryHaiku({
  systemPrompt, userPrompt, outputFormat, signal, options,
}): Promise<AssistantMessage> {
  const messages = [createUserMessage({ content: userPrompt })]
  const result = await queryModelWithoutStreaming({
    messages,
    systemPrompt,
    thinkingConfig: { type: 'disabled' },  // 关键：禁用 thinking
    tools: [],                              // 关键：无工具
    signal,
    options: {
      ...options,
      model: getSmallFastModel(),           // 关键：使用小模型
      enablePromptCaching: false,
      outputFormat,
      async getToolPermissionContext() {
        return getEmptyToolPermissionContext()
      },
    },
  })
  return result[0]
}
```

**关键设计决策**：
- 禁用 thinking（节省 token）
- 无工具调用（简化处理）
- 支持 JSON 结构化输出

**Brix 对应实现**：在 `side/manager.py` 中实现 `query_side()` 方法：

```python
async def query_side(
    self,
    user_prompt: str,
    system_prompt: str = "",
    json_schema: dict | None = None,
) -> str:
    """调用 side 模型执行轻量任务。"""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    response = await self._llm_client.chat(
        messages=messages,
        model=self._side_model,
    )
    return response.content or ""
```

### 4.3 工具摘要 — `toolUseSummaryGenerator.ts`

**文件**: `claude-code/src/services/toolUseSummary/toolUseSummaryGenerator.ts` (完整文件)

```typescript
const TOOL_USE_SUMMARY_SYSTEM_PROMPT = `Write a short summary label describing
what these tool calls accomplished. It appears as a single-line row in a mobile
app and truncates around 30 characters, so think git-commit-subject, not sentence.

Keep the verb in past tense and the most distinctive noun. Drop articles,
connectors, and long location context first.

Examples:
- Searched in auth/
- Fixed NPE in UserService
- Created signup endpoint
- Read config.json
- Ran failing tests`

export async function generateToolUseSummary({
  tools, signal, isNonInteractiveSession, lastAssistantText,
}: GenerateToolUseSummaryParams): Promise<string | null> {
  if (tools.length === 0) return null

  const toolSummaries = tools.map(tool => {
    const inputStr = truncateJson(tool.input, 300)
    const outputStr = truncateJson(tool.output, 300)
    return `Tool: ${tool.name}\nInput: ${inputStr}\nOutput: ${outputStr}`
  }).join('\n\n')

  const contextPrefix = lastAssistantText
    ? `User's intent (from assistant's last message): ${lastAssistantText.slice(0, 200)}\n\n`
    : ''

  const response = await queryHaiku({
    systemPrompt: TOOL_USE_SUMMARY_SYSTEM_PROMPT,
    userPrompt: `${contextPrefix}Tools completed:\n\n${toolSummaries}\n\nLabel:`,
    signal,
    options: { querySource: 'tool_use_summary_generation' },
  })
  return extractText(response) || null
}
```

**调用方式**：fire-and-forget，并行于下一轮主流式。

**Brix 实现要点**：
- 在 orchestrator 的 `tool_result` 事件后触发
- 异步执行，不阻塞主流程
- 结果只用于 CLI 显示（模型已经通过 tool_result 获得了完整信息）

### 4.4 会话标题 — `sessionTitle.ts`

**文件**: `claude-code/src/utils/sessionTitle.ts` (完整文件)

```typescript
const SESSION_TITLE_PROMPT = `Generate a concise, sentence-case title (3-7 words)
that captures the main topic or goal of this coding session. The title should be
clear enough that the user recognizes the session in a list. Use sentence case:
capitalize only the first word and proper nouns.

Return JSON with a single "title" field.

Good examples:
{"title": "Fix login button on mobile"}
{"title": "Add OAuth authentication"}
{"title": "Debug failing CI tests"}

Bad (too vague): {"title": "Code changes"}
Bad (too long): {"title": "Investigate and fix the issue where the login button..."}`

export async function generateSessionTitle(
  description: string, signal: AbortSignal,
): Promise<string | null> {
  const result = await queryHaiku({
    systemPrompt: SESSION_TITLE_PROMPT,
    userPrompt: description,
    outputFormat: { type: 'json_schema', schema: { ... } },
    signal,
    options: { querySource: 'generate_session_title' },
  })
  const parsed = JSON.parse(extractText(result))
  return parsed.title || null
}
```

**Brix 实现要点**：
- 在会话结束或 `/rename` 时调用
- 取会话前几条消息作为输入
- 输出 JSON `{"title": "..."}`
- 标题保存到 session metadata

### 4.5 偏好检测 — `skillImprovement.ts`

**文件**: `claude-code/src/utils/hooks/skillImprovement.ts` (行 85-190)

```typescript
function createSkillImprovementHook() {
  let lastAnalyzedCount = 0
  let lastAnalyzedIndex = 0

  const config = {
    name: 'skill_improvement',

    async shouldRun(context) {
      if (context.querySource !== 'repl_main_thread') return false
      // 每 TURN_BATCH_SIZE(5) 条用户消息运行一次
      const userCount = count(context.messages, m => m.type === 'user')
      if (userCount - lastAnalyzedCount < TURN_BATCH_SIZE) return false
      lastAnalyzedCount = userCount
      return true
    },

    buildMessages(context) {
      return [createUserMessage({
        content: `You are analyzing a conversation where a user is executing a skill.
Your job: identify if the user's recent messages contain preferences, requests,
or corrections that should be permanently added to the skill definition.

<skill_definition>${projectSkill.content}</skill_definition>
<recent_messages>${formatRecentMessages(newMessages)}</recent_messages>

Look for:
- Requests to add, change, or remove steps
- Preferences about how steps should work
- Corrections: "no, do X instead", "always use Y"

Ignore:
- Routine conversation that doesn't generalize
- Things the skill already does

Output a JSON array inside <updates> tags. Each item:
{"section": "...", "change": "...", "reason": "..."}
Output <updates>[]</updates> if no updates are needed.`,
      })]
    },

    getModel: getSmallFastModel,
  }
  return createApiQueryHook(config)
}
```

**Brix 实现要点**：
- 每 N 轮用户消息触发一次（可配置 interval）
- 分析最近的对话消息，检测偏好/纠正
- 检测到的偏好写入 `memory/data/user_prefs.md`
- 与 Brix 的 MemoryProvider 集成

### 4.6 离开摘要 — `awaySummary.ts`

**文件**: `claude-code/src/services/awaySummary.ts` (完整文件)

```typescript
const RECENT_MESSAGE_WINDOW = 30

const PROMPT_ZH = '用户离开后回来了。用中文写 1-3 句话。先说明用户在做什么
（高层目标，不是实现细节），然后说明下一步具体操作。不要写状态报告或提交总结。'

export async function generateAwaySummary(
  messages: readonly Message[], signal: AbortSignal,
): Promise<string | null> {
  const model = getSmallFastModel()
  const memory = await getSessionMemoryContent()
  const recent = messages.slice(-RECENT_MESSAGE_WINDOW)
  recent.push(createUserMessage({ content: buildAwaySummaryPrompt(memory) }))

  const response = await queryModelWithoutStreaming({
    messages: recent,
    systemPrompt: asSystemPrompt([]),
    thinkingConfig: { type: 'disabled' },
    tools: [],
    signal,
    options: { model, querySource: 'away_summary' },
  })
  return getAssistantMessageText(response)
}
```

### 4.7 历史搜索 — `agenticSessionSearch.ts`

**文件**: `claude-code/src/utils/agenticSessionSearch.ts` (行 15-48 系统提示)

```typescript
const SESSION_SEARCH_SYSTEM_PROMPT = `You are searching for relevant past sessions.
Given a user query and a list of candidate sessions, rank them by relevance.

Priority order:
1. Exact tag matches
2. Partial tag matches
3. Title matches
4. Branch name matches
5. Summary matches
6. Transcript content matches

Return a JSON array of relevant session indices, ordered by relevance.
If no sessions are relevant, return an empty array.`

export async function agenticSessionSearch(query, sessionLogs) {
  // 1. 先用关键词预过滤
  const candidates = sessionLogs.filter(log => logContainsQuery(log, query))
  // 2. 构建带编号的 session 列表
  const sessionList = candidates.map((log, i) => `${i}. ${log.title} ...`)
  // 3. 发给小模型做语义排序
  const response = await sideQuery({
    model: getSmallFastModel(),
    messages: [{ role: 'user', content: `Query: ${query}\n\nSessions:\n${sessionList}` }],
  })
  return JSON.parse(response).relevant_indices.map(i => candidates[i])
}
```

---

## 5. Side 层详细设计

### 5.1 抽象基类 — `side/base.py`

```python
"""SideTask 抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class SideTaskContext:
    """Side task 执行上下文。"""
    llm_client: Any          # LLMClient 实例
    side_model: str          # side 模型 ID
    config: dict             # 完整配置
    memory: Any              # MemoryProvider 实例
    session_messages: list   # 当前会话消息
    user_input: str          # 当前用户输入
    hooks: Any               # HookRegistry


class SideTask(ABC):
    """Side task 抽象基类。

    每个 side task 必须：
    1. 实现 name 属性（唯一标识符）
    2. 实现 execute() 方法
    3. 在 config 中有对应的开关
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """任务唯一标识符，与 config 中的 key 对应。"""
        ...

    def is_enabled(self, config: dict) -> bool:
        """检查该 task 是否在 config 中启用。默认从 side.tasks.{name}.enabled 读取。"""
        return config.get("side", {}).get("tasks", {}).get(self.name, {}).get("enabled", False)

    @abstractmethod
    async def execute(self, ctx: SideTaskContext) -> Any:
        """执行任务。返回值含义由各 task 自定义。"""
        ...
```

### 5.2 管理器 — `side/manager.py`

```python
"""SideTaskManager — 加载、调度、执行 side tasks。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)


class SideTaskManager:
    """管理所有 side tasks 的生命周期。

    设计原则：
    - 完全可选：没有 manager 或没有 task，agent 正常运行
    - 每个 task 独立开关
    - 失败不影响主流程（catch all exceptions）
    - 支持 fire-and-forget 模式
    """

    def __init__(self) -> None:
        self._tasks: dict[str, SideTask] = {}
        self._config: dict = {}
        self._side_model: str = ""
        self._llm_client: Any = None
        self._memory: Any = None
        self._user_message_count: int = 0  # 用于 pref_detection 间隔计数

    def configure(
        self,
        config: dict,
        llm_client: Any,
        memory: Any,
    ) -> None:
        """初始化 manager。在 BrixCLI.__init__() 中调用。"""
        self._config = config
        self._llm_client = llm_client
        self._memory = memory
        self._side_model = config.get("side", {}).get("model", "")

    def register(self, task: SideTask) -> None:
        """注册一个 side task。"""
        self._tasks[task.name] = task

    def _build_context(self, **kwargs) -> SideTaskContext:
        return SideTaskContext(
            llm_client=self._llm_client,
            side_model=self._side_model,
            config=self._config,
            memory=self._memory,
            session_messages=kwargs.get("session_messages", []),
            user_input=kwargs.get("user_input", ""),
            hooks=kwargs.get("hooks"),
        )

    def _is_task_enabled(self, task: SideTask) -> bool:
        """检查 task 是否启用（总开关 + 单 task 开关）。"""
        if not self._config.get("side", {}).get("enabled", False):
            return False
        if not self._side_model:
            return False
        return task.is_enabled(self._config)

    async def run_task(self, task_name: str, **kwargs) -> Any:
        """执行指定 task。失败返回 None，不影响主流程。"""
        task = self._tasks.get(task_name)
        if not task or not self._is_task_enabled(task):
            return None
        try:
            ctx = self._build_context(**kwargs)
            return await task.execute(ctx)
        except Exception as e:
            logger.warning(f"Side task '{task_name}' failed: {e}")
            return None

    def fire_and_forget(self, task_name: str, **kwargs) -> None:
        """异步执行 task，不等待结果。"""
        asyncio.create_task(self.run_task(task_name, **kwargs))

    def should_run_pref_detection(self) -> bool:
        """检查是否应该运行偏好检测（基于间隔）。"""
        interval = self._config.get("side", {}).get("tasks", {}).get(
            "pref_detection", {}
        ).get("interval", 5)
        return self._user_message_count > 0 and self._user_message_count % interval == 0

    def on_user_message(self) -> None:
        """用户消息计数器递增。"""
        self._user_message_count += 1

    def get_side_model(self) -> str:
        """返回 side 模型 ID。"""
        return self._side_model

    @property
    def enabled(self) -> bool:
        """side 层是否启用。"""
        return self._config.get("side", {}).get("enabled", False)
```

### 5.3 Task 实现 — `side/tasks/`

#### `session_title.py`

```python
"""会话标题生成。"""

from __future__ import annotations

import json
from side.base import SideTask, SideTaskContext

PROMPT = """\
Generate a concise title (3-7 words) that captures the main topic of this conversation.
Use sentence case. Return JSON with a single "title" field.

Examples:
{"title": "Fix login button on mobile"}
{"title": "Add OAuth authentication"}
{"title": "Debug failing CI tests"}"""


class SessionTitleTask(SideTask):
    @property
    def name(self) -> str:
        return "session_title"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        # 取前 3 条用户消息作为输入
        user_msgs = [
            m["content"] for m in ctx.session_messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ][:3]
        if not user_msgs:
            return None

        prompt_text = "\n".join(user_msgs)
        response = await ctx.llm_client.chat(
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": prompt_text},
            ],
            model=ctx.side_model,
        )
        try:
            data = json.loads(response.content)
            return data.get("title")
        except (json.JSONDecodeError, AttributeError):
            return None
```

#### `tool_summary.py`

```python
"""工具调用结果摘要。"""

from __future__ import annotations

import json
from side.base import SideTask, SideTaskContext

PROMPT = """\
Write a short summary label (under 30 chars) describing what these tool calls accomplished.
Think git-commit-subject, not sentence. Past tense. Drop articles.

Examples:
- Searched in auth/
- Fixed NPE in UserService
- Read config.json"""


class ToolSummaryTask(SideTask):
    @property
    def name(self) -> str:
        return "tool_summary"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        # ctx 中需要传入 tool_name, tool_input, tool_result
        tool_name = ctx.config.get("_side_task_args", {}).get("tool_name", "")
        tool_input = ctx.config.get("_side_task_args", {}).get("tool_input", {})
        tool_result = ctx.config.get("_side_task_args", {}).get("tool_result", "")

        # 截断过长的输入输出
        input_str = json.dumps(tool_input, ensure_ascii=False)[:300]
        output_str = str(tool_result)[:300]

        user_prompt = f"Tool: {tool_name}\nInput: {input_str}\nOutput: {output_str}\n\nLabel:"
        response = await ctx.llm_client.chat(
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            model=ctx.side_model,
        )
        return response.content.strip() if response.content else None
```

#### `pref_detection.py`

```python
"""用户偏好/习惯检测。"""

from __future__ import annotations

import json
import re
from side.base import SideTask, SideTaskContext

PROMPT = """\
分析以下对话，判断用户是否表达了偏好、纠正或习惯性要求。

寻找：
- 纠正："不要这样做"、"应该用..."、"下次记得..."
- 偏好："我喜欢..."、"我希望..."、"请总是..."
- 流程偏好："先...再..."、"帮我记住..."

忽略：
- 一次性的普通对话
- 已经在执行的操作

如果有发现，返回 JSON 数组，每项格式：
{"preference": "偏好描述", "context": "对话中的依据"}

如果没有发现，返回空数组：[]"""


class PrefDetectionTask(SideTask):
    @property
    def name(self) -> str:
        return "pref_detection"

    async def execute(self, ctx: SideTaskContext) -> list[dict] | None:
        # 取最近 10 条消息
        recent = ctx.session_messages[-10:]
        if len(recent) < 3:
            return None

        conversation = "\n".join(
            f"{'用户' if m.get('role') == 'user' else '助手'}: "
            f"{m.get('content', '')[:200]}"
            for m in recent
            if isinstance(m.get("content"), str)
        )

        response = await ctx.llm_client.chat(
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": conversation},
            ],
            model=ctx.side_model,
        )

        try:
            # 提取 JSON 数组
            content = response.content or "[]"
            # 尝试从 markdown code block 中提取
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                preferences = json.loads(match.group())
            else:
                preferences = json.loads(content)

            if preferences and ctx.memory:
                # 写入 user_prefs.md
                self._save_preferences(ctx, preferences)

            return preferences
        except (json.JSONDecodeError, AttributeError):
            return None

    def _save_preferences(self, ctx: SideTaskContext, preferences: list[dict]) -> None:
        """将检测到的偏好保存到 memory/data/user_prefs.md。"""
        prefs_path = ctx.memory._data_dir / "user_prefs.md"
        existing = ""
        if prefs_path.exists():
            existing = prefs_path.read_text()

        new_entries = []
        for pref in preferences:
            entry = f"- {pref.get('preference', '')} (依据: {pref.get('context', '')})"
            new_entries.append(entry)

        if new_entries:
            content = existing.rstrip() + "\n" + "\n".join(new_entries) + "\n"
            prefs_path.write_text(content)
```

#### `history_search.py`

```python
"""历史记忆语义搜索。"""

from __future__ import annotations

import json
from side.base import SideTask, SideTaskContext

TRIGGER_KEYWORDS = [
    "之前", "上次", "记得", "曾经", "以前", "那时候",
    "previously", "last time", "remember", "before",
]

PROMPT = """\
你是一个会话搜索助手。给定用户查询和一组候选历史会话，按相关性排序。

优先级：
1. 标题直接匹配
2. 内容语义匹配
3. 关键词部分匹配

返回 JSON 数组，包含相关会话的索引号（从 0 开始），按相关性降序排列。
如果没有相关会话，返回空数组：[]"""


class HistorySearchTask(SideTask):
    @property
    def name(self) -> str:
        return "history_search"

    def should_trigger(self, user_input: str) -> bool:
        """检查是否应该触发历史搜索。"""
        text = user_input.lower()
        return any(kw in text for kw in TRIGGER_KEYWORDS)

    async def execute(self, ctx: SideTaskContext) -> list[dict] | None:
        if not self.should_trigger(ctx.user_input):
            return None

        # 获取历史会话列表
        if not ctx.memory:
            return None

        sessions = ctx.memory.list_sessions()  # 需要 MemoryProvider 支持
        if not sessions:
            return None

        # 构建候选列表
        top_k = ctx.config.get("side", {}).get("tasks", {}).get(
            "history_search", {}
        ).get("top_k", 3)

        candidates = []
        for s in sessions[-20:]:  # 最近 20 个会话
            summary = s.get("summary", s.get("title", ""))
            candidates.append(f"标题: {s.get('title', '无标题')}\n摘要: {summary[:200]}")

        candidate_text = "\n---\n".join(candidates)
        user_prompt = f"用户查询: {ctx.user_input}\n\n候选会话:\n{candidate_text}"

        response = await ctx.llm_client.chat(
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            model=ctx.side_model,
        )

        try:
            indices = json.loads(response.content or "[]")
            results = []
            for i in indices[:top_k]:
                if 0 <= i < len(sessions):
                    results.append(sessions[i])
            return results
        except (json.JSONDecodeError, AttributeError):
            return None
```

#### `voice_cleanup.py`

```python
"""语音输入文本清理。"""

from __future__ import annotations

from side.base import SideTask, SideTaskContext

PROMPT = """\
清理以下语音识别文本：
1. 去除口语化填充词（嗯、啊、那个、就是说）
2. 修正明显的识别错误
3. 添加适当的标点符号
4. 保持原意不变

只返回清理后的文本，不要解释。"""


class VoiceCleanupTask(SideTask):
    @property
    def name(self) -> str:
        return "voice_cleanup"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        raw_text = ctx.config.get("_side_task_args", {}).get("raw_text", "")
        if not raw_text or len(raw_text) < 3:
            return raw_text

        response = await ctx.llm_client.chat(
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": raw_text},
            ],
            model=ctx.side_model,
        )
        return response.content.strip() if response.content else raw_text
```

#### `context_compress.py`

```python
"""长对话上下文压缩。"""

from __future__ import annotations

from side.base import SideTask, SideTaskContext

PROMPT = """\
将以下对话历史压缩为简明摘要，保留：
1. 关键决策和结论
2. 未完成的任务
3. 重要的上下文信息

丢弃：
- 重复的内容
- 已完成的中间步骤
- 礼貌性对话

输出 3-5 句话的摘要。"""


class ContextCompressTask(SideTask):
    @property
    def name(self) -> str:
        return "context_compress"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        threshold = ctx.config.get("side", {}).get("tasks", {}).get(
            "context_compress", {}
        ).get("message_threshold", 50)

        if len(ctx.session_messages) < threshold:
            return None

        # 取前半部分消息进行压缩
        half = len(ctx.session_messages) // 2
        old_messages = ctx.session_messages[:half]

        conversation = "\n".join(
            f"{'用户' if m.get('role') == 'user' else '助手'}: "
            f"{str(m.get('content', ''))[:300]}"
            for m in old_messages
            if isinstance(m.get("content"), str)
        )

        response = await ctx.llm_client.chat(
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": conversation},
            ],
            model=ctx.side_model,
        )
        return response.content if response.content else None
```

#### `session_summary.py`

```python
"""离开后回来的会话摘要。"""

from __future__ import annotations

from side.base import SideTask, SideTaskContext

PROMPT_ZH = """\
用户离开后回来了。用中文写 1-3 句话。
先说明用户在做什么（高层目标，不是实现细节），然后说明下一步具体操作。
不要写状态报告或提交总结。"""


class SessionSummaryTask(SideTask):
    @property
    def name(self) -> str:
        return "session_summary"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        if not ctx.session_messages:
            return None

        # 取最近 15 条消息
        recent = ctx.session_messages[-15:]
        conversation = "\n".join(
            f"{'用户' if m.get('role') == 'user' else '助手'}: "
            f"{str(m.get('content', ''))[:200]}"
            for m in recent
            if isinstance(m.get("content"), str)
        )

        response = await ctx.llm_client.chat(
            messages=[
                {"role": "system", "content": PROMPT_ZH},
                {"role": "user", "content": f"最近的对话:\n{conversation}"},
            ],
            model=ctx.side_model,
        )
        return response.content if response.content else None
```

### 5.4 包入口 — `side/__init__.py`

```python
"""Side 层 — 辅助任务执行层。

参考 Claude Code 的 Haiku "杂事"架构。
完全可选：没有 side 层，agent 也能正常运行。
"""

from side.base import SideTask, SideTaskContext
from side.manager import SideTaskManager

__all__ = ["SideTask", "SideTaskContext", "SideTaskManager"]
```

### 5.5 Tasks 包入口 — `side/tasks/__init__.py`

```python
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
```

---

## 6. Config 改造

### 6.1 settings.yaml 变更

**routing 部分简化**：

```yaml
# 改前
routing:
  default_model: "minimax/MiniMax-M2.7"
  fallback_model: "minimax/MiniMax-M2.7"
  chat_model: "zenmux-openai/deepseek/deepseek-v4-flash"    # 删除
  intent_model: "ali/qwen3.6-flash"                          # 删除

# 改后
routing:
  default_model: "minimax/MiniMax-M2.7"    # 主模型，/model 命令可切换
  fallback_model: "minimax/MiniMax-M2.7"   # 主模型不可用时的兜底
```

**新增 side 部分**：

```yaml
# ============================================================
# Side 层 — 辅助任务配置（完全可选）
# ============================================================
side:
  enabled: true
  model: "ali/qwen3.6-flash"           # side 任务专用小模型

  tasks:
    session_title:
      enabled: true
    tool_summary:
      enabled: true
    pref_detection:
      enabled: true
      interval: 5                       # 每 N 轮用户消息检测一次
    history_search:
      enabled: true
      top_k: 3
      trigger_keywords:
        - "之前"
        - "上次"
        - "记得"
        - "曾经"
        - "以前"
        - "previously"
        - "last time"
        - "remember"
    voice_cleanup:
      enabled: true
    context_compress:
      enabled: true
      message_threshold: 50
    session_summary:
      enabled: true
      idle_threshold_minutes: 5
```

### 6.2 model_registry.py

**保持不变**。ModelRegistry 的 `get_default_model()` 已经从 `routing.default_model` 读取，改造后依然适用。

### 6.3 loader.py

**保持不变**。ConfigLoader 的分层加载机制不需要修改。

---

## 7. Router 层处理

### 7.1 删除文件

```
router/intent.py          # 123 行，删除
router/complexity.py      # 33 行，删除
router/model_router.py    # 64 行，删除
router/__init__.py         # 2 行，删除
```

### 7.2 删除测试

```
tests/test_router.py      # 116 行，删除
```

### 7.3 更新 import

**cli/app.py** 中需要删除以下 import：

```python
# 删除
from router.intent import classify_intent
from router.complexity import evaluate_complexity
from router.model_router import select_model
```

---

## 8. CLI 层改造

### 8.1 cli/app.py — `_process_streaming()` 改造

**当前流程**（行 297-491）：

```
memory → intent → complexity → route → orchestrator
```

**目标流程**：

```
memory → [side: history_search] → orchestrator → [side: tool_summary, pref_detection]
```

**具体改动**：

#### 删除（行 324-346）：

```python
# 删除：Intent stage
intent_model = self._config.get("routing", {}).get("intent_model", "")
default_model = self._config.get("routing", {}).get("default_model", "")
_intent_model_name = (intent_model or default_model).split("/")[-1]
indicator.update("Intent", _intent_model_name)
trimmed = [m for m in context_messages if m.get("role") != "system"][-6:]
intent = await classify_intent(
    user_input, trimmed, self._llm_client,
    intent_model or default_model, hooks=hooks,
)
_tick("intent({})".format(intent))

# 删除：Complexity + Route stages
indicator.update("Complexity")
complexity = evaluate_complexity(user_input)
indicator.update("Route")
model = select_model(intent, complexity, self._config)
_tick("route->{}".format(model.split("/")[-1]))

hooks.fire("complexity", result=complexity)
hooks.fire("router", model=model, reason="{}->{}".format(intent, complexity))
log.set_model(model)
```

#### 替换为：

```python
# Side 层：历史搜索（如果触发）
if self._side_manager and self._side_manager.enabled:
    indicator.update("Side", "history_search")
    search_results = await self._side_manager.run_task(
        "history_search",
        session_messages=context_messages,
        user_input=user_input,
        hooks=hooks,
    )
    if search_results:
        # 将搜索结果注入到上下文
        search_summary = "\n".join(
            f"- {s.get('title', '无标题')}: {s.get('summary', '')[:100]}"
            for s in search_results
        )
        context_messages.append({
            "role": "user",
            "content": f"[系统] 以下是你之前的对话，可能与当前问题相关：\n{search_summary}",
        })
    _tick("side:history_search")

# 直接使用 config 中的主模型
model = self._config.get("routing", {}).get("default_model", "")
hooks.fire("router", model=model, reason="direct_config")
log.set_model(model)

# 用户消息计数（用于 pref_detection 间隔）
if self._side_manager:
    self._side_manager.on_user_message()
```

#### 修改 OrchestratorContext 构建（行 348-354）：

```python
# 改前
context = OrchestratorContext(
    history=list(context_messages),
    tool_runner=self._tool_runner,
    llm_client=self._llm_client,
    model=model,
    hooks=hooks,
)

# 改后（不变，model 现在来自 config 直接读取）
context = OrchestratorContext(
    history=list(context_messages),
    tool_runner=self._tool_runner,
    llm_client=self._llm_client,
    model=model,
    hooks=hooks,
)
```

#### 修改 StageIndicator（行 360）：

```python
# 改前
indicator.update("Planning", model.split("/")[-1])

# 改后
indicator.update("Planning", model.split("/")[-1])
```

#### 在 tool_result 事件后添加摘要（行 416-426）：

```python
elif event_type == "tool_result":
    tool_name = event.get("name", "unknown")
    elapsed_ms = event.get("ms", 0)
    is_err = event.get("is_error", False)
    tool_display.show_tool_result(
        tool_name,
        event.get("result", ""),
        elapsed_ms,
        is_error=is_err,
    )
    self._console.print()

    # 新增：fire-and-forget 工具摘要
    if self._side_manager and self._side_manager.enabled:
        self._side_manager.fire_and_forget(
            "tool_summary",
            session_messages=context_messages,
            user_input=user_input,
            hooks=hooks,
            # 传递工具信息（通过 kwargs 传入 SideTaskContext.config）
        )
```

#### 在持久化后添加偏好检测（行 478-484）：

```python
# 持久化本轮新增的完整消息
if not has_error:
    new_messages = context.history[original_history_count:]
    for msg in new_messages:
        if msg.get("role") != "system":
            self._memory.add_full_message(msg)
self._memory.save_session()

# 新增：偏好检测（按间隔触发）
if (self._side_manager and self._side_manager.enabled
        and self._side_manager.should_run_pref_detection()):
    self._side_manager.fire_and_forget(
        "pref_detection",
        session_messages=context_messages,
        user_input=user_input,
        hooks=hooks,
    )
```

### 8.2 cli/app.py — `__init__()` 改造

需要在 `BrixCLI.__init__()` 中初始化 SideTaskManager：

```python
# 在 _register_commands() 之后添加
self._side_manager = SideTaskManager()
self._side_manager.configure(
    config=self._config,
    llm_client=self._llm_client,
    memory=self._memory,
)
# 注册所有 tasks
from side.tasks import ALL_TASKS
for task in ALL_TASKS:
    self._side_manager.register(task)
```

### 8.3 cli/app.py — 语音清理集成

当前语音清理代码在 `cli/app.py` 行 522-530：

```python
cleanup_model = self._config.get("routing", {}).get("intent_model", "ali/qwen3.6-flash")

async def _cleanup_llm(prompt: str) -> str:
    resp = await self._llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        model=cleanup_model,
    )
    return resp.content
```

**改为**：

```python
async def _cleanup_llm(prompt: str) -> str:
    if self._side_manager and self._side_manager.enabled:
        result = await self._side_manager.run_task(
            "voice_cleanup",
            session_messages=[],
            user_input="",
            # 传递 raw_text
        )
        if result:
            return result
    # fallback：直接调用 side 模型
    side_model = self._side_manager.get_side_model() if self._side_manager else "ali/qwen3.6-flash"
    resp = await self._llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        model=side_model,
    )
    return resp.content
```

### 8.4 StageIndicator 更新

当前有 4 个阶段：`Intent`, `Complexity`, `Route`, `Planning`

改为 2 个阶段：`Side`（可选）, `Planning`

---

## 9. /model 命令改造

### 9.1 当前实现

**文件**: `capability/command/builtin/info.py` (行 51-68)

当前 `/model` 只读取配置显示，不支持切换。

### 9.2 目标实现

```python
class ModelCommand(Command):
    """查看或切换主模型。"""

    def __init__(self, config: dict) -> None:
        self._config = config

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="model",
            description="查看或切换主模型 (/model [model_id])",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        # 无参数：显示当前模型和可用模型列表
        if not args.strip():
            default_model = self._config.get("routing", {}).get("default_model", "unknown")
            print(f"\n  当前主模型: {default_model}")
            print(f"\n  可用模型:")
            for model in self._config.get("models", []):
                model_id = model.get("id", "")
                purposes = ", ".join(model.get("purpose", []))
                cost = model.get("cost_tier", "?")
                marker = " *" if model_id == default_model else ""
                print(f"    {model_id} [{cost}]{marker}")
            print("\n  使用 /model <model_id> 切换模型")
            print("  使用 /model save 持久化当前会话的模型到 settings.local.yaml\n")
            return CommandResult(type=CommandResultType.NONE)

        # "save" 参数：持久化到 settings.local.yaml
        if args.strip().lower() == "save":
            return await self._save_model(context)

        # 有参数：切换模型
        model_id = args.strip()
        # 验证模型存在
        models = self._config.get("models", [])
        valid_ids = {m.get("id") for m in models}
        if model_id not in valid_ids:
            print(f"\n  未知模型: {model_id}")
            print(f"  使用 /model 查看可用模型列表\n")
            return CommandResult(type=CommandResultType.NONE)

        # 运行时切换（不持久化）
        self._config.setdefault("routing", {})["default_model"] = model_id
        print(f"\n  已切换到: {model_id}")
        print(f"  使用 /model save 持久化此更改\n")
        return CommandResult(type=CommandResultType.NONE)

    async def _save_model(self, context: CommandContext) -> CommandResult:
        """将当前模型设置持久化到 settings.local.yaml。"""
        from pathlib import Path
        import yaml

        current_model = self._config.get("routing", {}).get("default_model", "")
        if not current_model:
            print("\n  没有可保存的模型设置\n")
            return CommandResult(type=CommandResultType.NONE)

        # 写入 .brix/settings.local.yaml（项目级）
        local_path = Path.cwd() / ".brix" / "settings.local.yaml"
        local_path.parent.mkdir(parents=True, exist_ok=True)

        existing = {}
        if local_path.exists():
            with open(local_path) as f:
                existing = yaml.safe_load(f) or {}

        existing.setdefault("routing", {})["default_model"] = current_model

        with open(local_path, "w") as f:
            yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)

        print(f"\n  已持久化到 {local_path}")
        print(f"  主模型: {current_model}\n")
        return CommandResult(type=CommandResultType.NONE)
```

### 9.3 静态命令列表更新

**文件**: `capability/basics/commands.py`

需要更新 `COMMANDS` 列表中 `/model` 的描述：

```python
("model", "查看或切换主模型 (/model [model_id])"),
```

---

## 10. 实施阶段规划

### 阶段 1：Side 层骨架（基础设施）

**目标**：建立 side 层的基本结构，不接入主流程

**任务**：
1. 创建 `side/` 目录结构
2. 实现 `side/base.py`（SideTask, SideTaskContext）
3. 实现 `side/manager.py`（SideTaskManager）
4. 实现 `side/__init__.py` 和 `side/tasks/__init__.py`
5. 编写 unit tests

**验收**：side 模块可以独立 import，SideTaskManager 可以注册和执行 task

### 阶段 2：Config 改造

**目标**：更新配置结构，支持 side 层配置

**任务**：
1. 修改 `config/settings.yaml`：简化 routing，新增 side 块
2. 验证 `config/loader.py` 正确加载新配置
3. 验证 `config/model_registry.py` 在新配置下正常工作

**验收**：`load_config()` 正确返回包含 side 块的配置

### 阶段 3：实现 7 个 Side Tasks

**目标**：逐个实现所有 side tasks

**任务**（可并行）：
1. `side/tasks/session_title.py`
2. `side/tasks/tool_summary.py`
3. `side/tasks/pref_detection.py`
4. `side/tasks/history_search.py`
5. `side/tasks/voice_cleanup.py`
6. `side/tasks/context_compress.py`
7. `side/tasks/session_summary.py`

**验收**：每个 task 可以独立调用 LLM 并返回预期结果

### 阶段 4：CLI 集成

**目标**：将 side 层接入主流程

**任务**：
1. 修改 `cli/app.py` 的 `__init__()`：初始化 SideTaskManager
2. 修改 `_process_streaming()`：移除 intent/complexity/route，接入 side
3. 集成 tool_summary（fire-and-forget）
4. 集成 pref_detection（间隔触发）
5. 集成 history_search（关键词触发）
6. 更新 StageIndicator
7. 修改语音清理使用 side 层

**验收**：`brix` 启动后正常对话，side tasks 按配置执行

### 阶段 5：/model 命令改造

**目标**：支持模型切换和持久化

**任务**：
1. 改造 `capability/command/builtin/info.py` 的 ModelCommand
2. 更新 `capability/basics/commands.py` 的静态列表
3. 编写测试

**验收**：`/model` 显示模型列表，`/model <id>` 切换，`/model save` 持久化

### 阶段 6：清理

**目标**：删除旧代码，确保无残留

**任务**：
1. 删除 `router/` 目录
2. 删除 `tests/test_router.py`
3. 更新 `cli/app.py` 的 import
4. 运行完整测试套件
5. 更新 CLAUDE.md（如有必要）

**验收**：无 import 错误，所有测试通过，`brix` 正常运行

---

## 11. 测试策略

### 单元测试

每个 side task 需要独立的单元测试：

```
tests/side/
  __init__.py
  test_manager.py
  test_session_title.py
  test_tool_summary.py
  test_pref_detection.py
  test_history_search.py
  test_voice_cleanup.py
  test_context_compress.py
  test_session_summary.py
```

测试模式：
- Mock `LLMClient.chat()` 返回预设响应
- 验证 task 正确解析响应
- 验证 task 在异常时返回 None（不崩溃）
- 验证 `is_enabled()` 正确读取 config

### 集成测试

验证 SideTaskManager 与 cli/app.py 的集成：
- Mock orchestrator 返回工具调用事件
- 验证 tool_summary 被触发
- 验证 pref_detection 按间隔触发
- 验证 history_search 在关键词出现时触发

### 回归测试

验证改造后主流程不受影响：
- `brix` 启动正常
- 对话正常（无 side 层时）
- `/model` 命令正常
- 语音模式正常

---

## 12. 附录：完整代码参考

### A. Claude Code 关键文件索引

| 文件路径 | 关键内容 |
|---------|---------|
| `src/utils/model/model.ts:42-56` | `getSmallFastModel()` — 小模型选择 |
| `src/services/api/claude.ts:3421-3473` | `queryHaiku()` — 小模型查询封装 |
| `src/services/toolUseSummary/toolUseSummaryGenerator.ts` | 工具摘要完整实现 |
| `src/utils/sessionTitle.ts` | 会话标题完整实现 |
| `src/services/awaySummary.ts` | 离开摘要完整实现 |
| `src/utils/agenticSessionSearch.ts` | 历史搜索完整实现 |
| `src/utils/hooks/skillImprovement.ts:85-190` | 偏好检测核心逻辑 |
| `src/utils/sideQuery.ts:45-85` | SideQueryOptions 类型定义 |

### B. Brix 关键文件索引

| 文件路径 | 关键内容 | 改造影响 |
|---------|---------|---------|
| `cli/app.py:297-491` | `_process_streaming()` 主流程 | 大改 |
| `cli/app.py:618-652` | `_register_commands()` | 小改（初始化 side） |
| `capability/command/builtin/info.py:51-68` | ModelCommand | 大改 |
| `config/settings.yaml:178-182` | routing 配置 | 大改 |
| `config/model_registry.py` | 模型查找 | 不变 |
| `config/loader.py` | 配置加载 | 不变 |
| `router/intent.py` | intent 分类 | 删除 |
| `router/complexity.py` | 复杂度评估 | 删除 |
| `router/model_router.py` | 模型路由 | 删除 |
| `tests/test_router.py` | router 测试 | 删除 |

### C. 新增文件清单

| 文件路径 | 行数估计 | 说明 |
|---------|---------|------|
| `side/__init__.py` | ~15 | 包入口 |
| `side/base.py` | ~45 | 抽象基类 |
| `side/manager.py` | ~100 | 管理器 |
| `side/tasks/__init__.py` | ~25 | 任务注册 |
| `side/tasks/session_title.py` | ~40 | 会话标题 |
| `side/tasks/tool_summary.py` | ~45 | 工具摘要 |
| `side/tasks/pref_detection.py` | ~75 | 偏好检测 |
| `side/tasks/history_search.py` | ~70 | 历史搜索 |
| `side/tasks/voice_cleanup.py` | ~30 | 语音清理 |
| `side/tasks/context_compress.py` | ~45 | 上下文压缩 |
| `side/tasks/session_summary.py` | ~35 | 会话摘要 |
| `tests/side/__init__.py` | ~0 | 测试包 |
| `tests/side/test_manager.py` | ~80 | 管理器测试 |
| `tests/side/test_tasks.py` | ~150 | 所有 task 测试 |

### D. SideTaskContext 扩展机制

当需要向 task 传递额外参数时，使用 `kwargs` 机制：

```python
# 调用方
await manager.run_task(
    "tool_summary",
    session_messages=messages,
    user_input=input,
    # 以下 kwargs 会进入 SideTaskContext.config["_side_task_args"]
    tool_name="Bash",
    tool_input={"command": "ls"},
    tool_result="file1.txt\nfile2.txt",
)

# task 内部
tool_name = ctx.config.get("_side_task_args", {}).get("tool_name", "")
```

这种设计避免了 SideTaskContext 的字段膨胀，保持基类简洁。

### E. 错误处理原则

所有 side task 都遵循"静默失败"原则：

```python
try:
    result = await task.execute(ctx)
    return result
except Exception as e:
    logger.warning(f"Side task '{task_name}' failed: {e}")
    return None  # 不抛出，不影响主流程
```

这意味着：
- LLM 调用超时 → 返回 None
- JSON 解析失败 → 返回 None
- 网络错误 → 返回 None
- 任何未预期的异常 → 返回 None

主流程完全不受 side task 失败影响。
