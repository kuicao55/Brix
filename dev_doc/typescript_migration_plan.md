# Brix Python -> TypeScript 完整迁移计划

> **目标**：将 Brix 从 Python 3.11+ 全面迁移至 TypeScript，保持当前分层架构（Protocol 接口隔离）和所有已实现功能不变。
>
> **参考项目**：`/Users/kuicao/Applications/claude_codes/claude-code`（TypeScript + Bun + ESM）
>
> **迁移后 CLI 入口**：终端输入 `brix` 即可启动（通过 npm/bun `bin` 字段注册）

---

## 一、技术选型

### 1.1 运行时与构建

| 决策项 | 选择 | 理由 |
|--------|------|------|
| **运行时** | Bun (>=1.3.0) | 启动速度快、原生 TypeScript 支持、与参考项目一致 |
| **模块系统** | ESM (`"type": "module"`) | 参考项目惯例，原生 async/await |
| **TypeScript 配置** | `target: ESNext`, `module: ESNext`, `strict: true`, `moduleResolution: bundler` | 参考项目标准配置 |
| **构建工具** | Bun.build() 单文件打包 | 生成 `dist/cli.js`，shebang `#!/usr/bin/env bun` |
| **包管理** | npm (package.json) | 标准分发，`bin.brix` 指向 `dist/cli.js` |

### 1.2 依赖映射

| Python 依赖 | TypeScript 替代 | 用途 |
|-------------|----------------|------|
| `pyyaml` | `js-yaml` + `@types/js-yaml` | YAML 配置解析 |
| `openai` | `openai` (npm) | OpenAI 兼容 API |
| `anthropic` | `@anthropic-ai/sdk` (npm) | Anthropic API |
| `prompt-toolkit` | `@inquirer/prompts` + `chalk` + `ora` | REPL 交互、颜色、spinner |
| `rich` | `chalk` (颜色) + `marked` + `marked-terminal` (Markdown 终端渲染) + 自定义组件 | 终端 UI |
| `tiktoken` | `js-tiktoken` | Token 计数 |
| `tenacity` | 自实现 `retry()` 工具函数 (p-retry 或手动) | 重试逻辑 |
| `python-dotenv` | `dotenv` (npm) | .env 加载 |
| `httpx` | (不需要，SDK 自带) | — |
| `fcntl` | `proper-lockfile` | 文件锁 |
| `uuid` | `crypto.randomUUID()` | UUID 生成 |

### 1.3 开发依赖

| 用途 | 包 |
|------|---|
| 测试 | `vitest` (替代 pytest) |
| 类型检查 | `typescript` (tsc --noEmit) |
| Lint | `@biomejs/biome` (参考项目惯例) |

---

## 二、目录结构映射

### 2.1 当前 Python 结构 -> TypeScript 结构

**核心原则**：每个模块自包含 — 逻辑代码和运行时数据在同一个文件夹下，与 Python 版结构完全一致。

```
Brix/
├── main.py                    -> src/entrypoints/cli.ts     (CLI 入口)
├── pyproject.toml             -> package.json + tsconfig.json
├── CLAUDE.md                  -> CLAUDE.md                  (更新语言相关约束)
│
│   ── 以下是 src/ 下的模块，每个模块自包含 ──
│
├── src/
│   ├── config/
│   │   ├── loader.ts                ← config/loader.py
│   │   ├── model-registry.ts        ← config/model_registry.py
│   │   └── settings.yaml            ← config/settings.yaml (数据文件跟着模块走)
│   │
│   ├── infra/
│   │   ├── llm-client.ts            ← infra/llm_client.py
│   │   └── providers/
│   │       ├── openai-compat.ts     ← infra/providers/openai_compat.py
│   │       └── anthropic-compat.ts  ← infra/providers/anthropic_compat.py
│   │
│   ├── router/
│   │   ├── intent.ts                ← router/intent.py
│   │   ├── complexity.ts            ← router/complexity.py
│   │   └── model-router.ts          ← router/model_router.py
│   │
│   ├── orchestrator/
│   │   ├── engine.ts                ← orchestrator/engine.py (接口定义)
│   │   ├── states.ts                ← orchestrator/states.py
│   │   ├── state-machine.ts         ← orchestrator/state_machine.py
│   │   └── langgraph-engine.ts      ← orchestrator/langgraph_engine.py (可选)
│   │
│   ├── capability/
│   │   ├── base.ts                  ← capability/base.py (Tool 接口)
│   │   ├── runner.ts                ← capability/runner.py
│   │   ├── basics/
│   │   │   ├── commands.ts          ← capability/basics/commands.py
│   │   │   ├── logs.ts              ← capability/basics/logs.py
│   │   │   ├── memory-files.ts      ← capability/basics/memory_files.py
│   │   │   └── sessions.ts          ← capability/basics/sessions.py
│   │   └── tools/
│   │       ├── calculator.ts        ← capability/tools/calculator.py
│   │       ├── weather.ts           ← capability/tools/weather.py
│   │       ├── file-read.ts         ← capability/tools/file_read.py
│   │       ├── file-write.ts        ← capability/tools/file_write.py
│   │       └── file-edit.ts         ← capability/tools/file_edit.py
│   │
│   ├── memory/
│   │   ├── types.ts                 ← memory/__init__.py (MemoryProvider 接口)
│   │   ├── provider.ts              ← memory/provider.py
│   │   ├── session.ts               ← memory/session.py
│   │   ├── soul.ts                  ← memory/soul.py
│   │   ├── user.ts                  ← memory/user.py
│   │   ├── storage.ts               ← memory/storage.py
│   │   ├── strategy.ts              ← memory/strategy.py
│   │   └── data/                    ← memory/data/ (数据文件跟着模块走)
│   │       ├── soul.md
│   │       ├── user.md
│   │       └── sessions/
│   │           ├── index.json
│   │           └── session-*.json
│   │
│   ├── log/
│   │   ├── flow.ts                  ← log/flow.py
│   │   ├── writer.ts                ← log/writer.py
│   │   └── data/                    ← log/data/ (数据文件跟着模块走)
│   │       └── brix.jsonl
│   │
│   ├── hooks/
│   │   └── registry.ts              ← hooks/registry.py
│   │
│   └── cli/
│       ├── app.ts                   ← cli/app.py (主 REPL 类)
│       ├── banner.ts                ← cli/banner.py
│       ├── completer.ts             ← cli/completer.py
│       ├── display.ts               ← cli/display.py
│       ├── paginated-selector.ts    ← cli/paginated_selector.py
│       ├── spinner.ts               ← cli/spinner.py
│       ├── stage-indicator.ts       ← cli/stage_indicator.py
│       ├── stream-renderer.ts       ← cli/stream_renderer.py
│       ├── theme.ts                 ← cli/theme.py
│       └── tool-display.ts          ← cli/tool_display.py
│
├── tests/                           (vitest 格式，结构与 src/ 对应)
├── dev_doc/
├── package.json
├── tsconfig.json
├── .env / .env.example
└── .gitignore                       (加入 src/memory/data/, src/log/data/)
```

**与 Python 版对比**：模块分类完全不变，每个文件夹的职责不变。只是所有源码统一收入 `src/` 目录，数据文件跟着各自模块走。

### 2.2 文件命名规范

- TypeScript 文件使用 **kebab-case**（如 `llm-client.ts`），与参考项目一致
- 类型定义文件使用 `types.ts` 后缀
- 测试文件使用 `*.test.ts` 后缀（vitest 约定）

---

## 三、核心类型定义（Protocol -> Interface）

### 3.1 全局类型文件 `src/types.ts`

```typescript
/** 消息格式 — 贯穿 memory/orchestrator/infra 层 */
export type Message = {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  tool_calls?: ToolCallData[]
  tool_call_id?: string
  tool_name?: string
  timestamp?: string
}

/** LLM 返回的工具调用 */
export type ToolCallData = {
  id: string
  name: string
  arguments: Record<string, unknown>
}

/** LLM 响应 */
export type LLMResponse = {
  content: string
  tool_calls: ToolCallData[]
  finish_reason: string
}

/** 流式事件 */
export type StreamEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'tool_call'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; id: string; name: string; result: string; ms: number; is_error: boolean }

/** 会话索引条目 */
export type SessionIndexEntry = {
  id: string
  created: string
  updated: string
  message_count: number
  preview: string
}

/** Hook 事件 */
export type HookEvent = {
  name: string
  data: Record<string, unknown>
}
```

### 3.2 MemoryProvider 接口 `src/memory/types.ts`

```typescript
export interface MemoryProvider {
  loadSoul(): string
  loadUserMemory(): string
  soulExists(): boolean
  userMemoryExists(): boolean
  createSession(): string
  clearSession(): void
  addMessage(role: string, content: string): void
  saveSession(): void
  loadSession(sessionId: string): Message[]
  resumeSession(sessionId: string): Message[]
  listSessions(): SessionIndexEntry[]
  getContextMessages(systemPrompt: string): Message[]
  buildSystemPrompt(sessionContext?: string, dynamicContext?: string): string
}
```

### 3.3 OrchestratorEngine 接口 `src/orchestrator/engine.ts`

```typescript
export interface ToolRunner {
  run(toolName: string, params: Record<string, unknown>): Promise<string>
  getToolSchemas(): Record<string, unknown>[]
}

export type OrchestratorContext = {
  history: Message[]
  memory: Record<string, unknown>
  toolRunner: ToolRunner | null
  llmClient: LLMClient | null
  model: string
  hooks: HookRegistry | null
}

export interface OrchestratorEngine {
  run(userInput: string, context: OrchestratorContext): Promise<string>
  runStream(userInput: string, context: OrchestratorContext): AsyncGenerator<StreamEvent>
}
```

### 3.4 Tool 接口 `src/capability/base.ts`

```typescript
export interface Tool {
  readonly name: string
  readonly description: string
  readonly inputSchema: Record<string, unknown>
  execute(params: Record<string, unknown>): Promise<string>
  toOpenAiSchema(): Record<string, unknown>
}
```

---

## 四、逐层迁移详细方案

### 4.1 Config 层

#### `src/config/loader.ts`

**Python 原逻辑**：
- `ConfigLoader` 类：分层 YAML 合并（global -> project -> local -> fallback）
- `load_config()` 函数：检测 `.brix/` 目录，返回合并后的配置 dict

**TypeScript 实现要点**：
```typescript
import yaml from 'js-yaml'
import fs from 'fs'
import path from 'path'

export type BrixConfig = {
  providers: Record<string, ProviderConfig>
  models: ModelConfig[]
  engine: string
  routing: { default_model: string; fallback_model: string }
  retry: { max_retries: number; base_delay: number; max_delay: number }
  memory: { data_dir: string; max_context_tokens: number }
}

export type ProviderConfig = {
  base_url: string
  api_key_env: string
  protocol: 'openai' | 'anthropic'
}

export type ModelConfig = {
  id: string
  provider: string
  purpose: string[]
  capabilities: string[]
  max_context: number
  cost_tier: string
  default?: boolean
}
```

- 使用 `js-yaml` 的 `yaml.load()` 替代 `yaml.safe_load()`
- 深度合并使用递归函数，逻辑与 Python 版完全一致
- 文件路径使用 `path.join()` / `path.resolve()`
- 读文件用 `fs.readFileSync()` (同步，初始化阶段)
- **默认 data_dir** 为 `src/memory/data`（相对于项目根目录），对应 Python 版的 `memory/data`

#### `src/config/model-registry.ts`

**Python 原逻辑**：
- `ModelRegistry` 类：`get_model_by_id()`, `get_default_model()`, `get_fallback_model()`, `get_models_by_purpose()`

**TypeScript 实现要点**：
- 直接移植逻辑，用 `Map<string, ModelConfig>` 做索引
- 类型安全：返回 `ModelConfig | undefined` 而非 `dict | None`

---

### 4.2 Infra 层

#### `src/infra/llm-client.ts`

**Python 原逻辑**：
- `ToolCall` / `LLMResponse` dataclass -> 已定义为 TypeScript type
- `LLMClient` 类：懒加载 provider、retry with tenacity、fallback model
- `_is_retryable()` 判断异常类型

**TypeScript 实现要点**：
```typescript
import type { LLMResponse, ToolCallData } from '../types.js'

export class LLMClient {
  private providersConfig: Record<string, ProviderConfig>
  private providers: Map<string, Provider> = new Map()
  private retryConfig: { max_retries: number; base_delay: number; max_delay: number }
  private routingConfig: { default_model: string; fallback_model: string }

  constructor(config: BrixConfig) { ... }

  async chat(messages: Message[], model: string, tools?: Record<string, unknown>[]): Promise<LLMResponse> { ... }
  async *chatStream(messages: Message[], model: string, tools?: Record<string, unknown>[]): AsyncGenerator<StreamEvent> { ... }
}
```

**重试逻辑**（替代 tenacity）：
```typescript
async function retry<T>(
  fn: () => Promise<T>,
  options: { retries: number; baseDelay: number; maxDelay: number; isRetryable: (e: unknown) => boolean }
): Promise<T> {
  for (let attempt = 0; attempt <= options.retries; attempt++) {
    try {
      return await fn()
    } catch (e) {
      if (attempt === options.retries || !options.isRetryable(e)) throw e
      const delay = Math.min(options.baseDelay * Math.pow(2, attempt), options.maxDelay)
      await new Promise(r => setTimeout(r, delay * 1000))
    }
  }
  throw new Error('unreachable')
}
```

**`_isRetryable()` 逻辑**：
- 检查异常是否为 SDK 的 `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `InternalServerError`
- 检查 `status_code` 是否为 5xx
- 不重试 4xx/auth 错误

#### `src/infra/providers/openai-compat.ts`

**Python 原逻辑**：
- `OpenAICompatProvider`：使用 `AsyncOpenAI` SDK
- `chat()`: 非流式调用，解析 tool_calls
- `chat_stream()`: 流式调用，累积 tool_call deltas

**TypeScript 实现要点**：
```typescript
import OpenAI from 'openai'

export class OpenAICompatProvider {
  async chat(params: {
    messages: Message[], model: string, tools?: Record<string, unknown>[],
    baseUrl: string, apiKey: string
  }): Promise<LLMResponse> { ... }

  async *chatStream(params: {
    messages: Message[], model: string, tools?: Record<string, unknown>[],
    baseUrl: string, apiKey: string
  }): AsyncGenerator<StreamEvent> { ... }
}
```

- 使用 `openai` npm 包的 `new OpenAI({ baseURL, apiKey })`
- 流式：`stream = await client.chat.completions.create({ stream: true, ... })`，然后 `for await (const chunk of stream)`
- tool_call 参数解析：JSON string -> `JSON.parse()`，已解析 dict -> 直接用，解析失败 -> `{ raw: string }`

#### `src/infra/providers/anthropic-compat.ts`

**Python 原逻辑**：
- `AnthropicCompatProvider`：使用 `AsyncAnthropic` SDK
- 消息格式转换：OpenAI format -> Anthropic format（system 提取、tool_use/tool_result 块）
- 工具 schema 转换：OpenAI function schema -> Anthropic input_schema

**TypeScript 实现要点**：
```typescript
import Anthropic from '@anthropic-ai/sdk'

export class AnthropicCompatProvider {
  async chat(params: {
    messages: Message[], model: string, tools?: Record<string, unknown>[],
    baseUrl: string, apiKey: string
  }): Promise<LLMResponse> { ... }

  async *chatStream(params: {
    messages: Message[], model: string, tools?: Record<string, unknown>[],
    baseUrl: string, apiKey: string
  }): AsyncGenerator<StreamEvent> { ... }

  private convertMessages(messages: Message[]): { system: string; messages: AnthropicMessage[] } { ... }
  private convertTools(tools: Record<string, unknown>[]): AnthropicTool[] { ... }
}
```

**关键转换逻辑**（必须完全移植）：
1. `convertMessages()`:
   - 提取 `role === 'system'` 消息的 content 作为顶层 `system` 参数
   - `role === 'user'` -> `{ role: 'user', content: string }`
   - `role === 'assistant'` 带 `tool_calls` -> `{ role: 'assistant', content: [{type: 'text', text}, {type: 'tool_use', id, name, input}] }`
   - `role === 'tool'` -> `{ role: 'user', content: [{type: 'tool_result', tool_use_id, content}] }`
2. `convertTools()`:
   - `{ name, description, input_schema }` -> `{ name, description, input_schema }` (Anthropic 格式直接用 input_schema)
   - OpenAI 格式：`{ type: 'function', function: { name, description, parameters } }` -> 提取 function 内容

---

### 4.3 Router 层

#### `src/router/intent.ts`

**Python 原逻辑**：
- `classify_intent()` async 函数
- 先尝试 LLM 分类（system prompt: "classify as chat/task/tool_use"）
- 失败时回退到关键词启发式
- 触发 "intent" hook 事件

**TypeScript 实现要点**：
- 逻辑完全一致，LLM 调用使用 `LLMClient.chat()`
- 关键词列表保持一致

#### `src/router/complexity.ts`

**Python 原逻辑**：
- `evaluate_complexity()` 同步函数
- 基于词数和关键词返回 "low"/"medium"/"high"

**TypeScript 实现要点**：
- 直接移植，纯函数，无外部依赖

#### `src/router/model-router.ts`

**Python 原逻辑**：
- `select_model()` 同步函数
- high complexity -> reasoning models, task intent -> coding models, else -> default

**TypeScript 实现要点**：
- 直接移植，引用 config 中的 routing 配置

---

### 4.4 Orchestrator 层

#### `src/orchestrator/states.ts`

```typescript
export const OrchestratorState = {
  IDLE: 'idle',
  PLANNING: 'planning',
  EXECUTING: 'executing',
  REVIEWING: 'reviewing',
  RESPONDING: 'responding',
} as const

export type OrchestratorState = typeof OrchestratorState[keyof typeof OrchestratorState]
```

#### `src/orchestrator/state-machine.ts`

**Python 原逻辑**：
- `StateMachineOrchestrator` 类
- `run()`: plan -> if no tool_calls -> respond, else execute -> loop
- `run_stream()`: async generator yielding events
- 合成 tool_call ID（provider 返回 None 时）
- 触发 "orch_plan" 和 "tool_exec" hooks
- max_iterations 默认 100

**TypeScript 实现要点**：
```typescript
export class StateMachineOrchestrator implements OrchestratorEngine {
  private maxIterations: number

  constructor(maxIterations = 100) { ... }

  async run(userInput: string, context: OrchestratorContext): Promise<string> { ... }

  async *runStream(userInput: string, context: OrchestratorContext): AsyncGenerator<StreamEvent> { ... }
}
```

- `async *runStream()` 使用 TypeScript async generator，与 Python `AsyncGenerator` 一一对应
- `yield { type: 'text_delta', text }` 等事件格式保持一致
- 合成 ID：`"call_" + crypto.randomUUID().replace(/-/g, '').slice(0, 12)`

#### `src/orchestrator/langgraph-engine.ts`（可选）

**注意**：LangGraph 的 JS/TS SDK (`@langchain/langgraph`) 与 Python 版 API 差异较大。建议：
- **第一阶段**：只迁移 `StateMachineOrchestrator`（功能完全一致）
- **第二阶段**（可选）：如果需要 LangGraph，使用 `@langchain/langgraph` 重写

---

### 4.5 Capability 层

#### `src/capability/base.ts`

```typescript
export interface Tool {
  readonly name: string
  readonly description: string
  readonly inputSchema: Record<string, unknown>
  execute(params: Record<string, unknown>): Promise<string>
  toOpenAiSchema(): Record<string, unknown>
}

/** 便捷基类（可选，减少样板代码） */
export abstract class BaseTool implements Tool {
  abstract readonly name: string
  abstract readonly description: string
  abstract readonly inputSchema: Record<string, unknown>
  abstract execute(params: Record<string, unknown>): Promise<string>

  toOpenAiSchema(): Record<string, unknown> {
    return {
      type: 'function',
      function: {
        name: this.name,
        description: this.description,
        parameters: this.inputSchema,
      },
    }
  }
}
```

#### `src/capability/runner.ts`

```typescript
import type { Tool } from './base.js'
import type { ToolRunner as ToolRunnerProtocol } from '../orchestrator/engine.js'

export class ToolRunner implements ToolRunnerProtocol {
  private tools: Map<string, Tool> = new Map()

  register(tool: Tool): void {
    this.tools.set(tool.name, tool)
  }

  async run(toolName: string, params: Record<string, unknown>): Promise<string> {
    const tool = this.tools.get(toolName)
    if (!tool) throw new Error(`Unknown tool: ${toolName}`)
    return await tool.execute(params)
  }

  getToolSchemas(): Record<string, unknown>[] {
    return [...this.tools.values()].map(t => t.toOpenAiSchema())
  }
}
```

#### `src/capability/tools/calculator.ts`

**Python 原逻辑**：
- AST 安全数学求值器（支持 +, -, *, /, %, **, 一元 +/-)
- DoS 保护：max depth 20, max nodes 100, exponent cap 1000

**TypeScript 实现要点**：
- 使用 `node:vm` 或自实现递归下降解析器（TypeScript 没有 `ast.literal_eval`）
- 推荐：手写简单的递归下降解析器，安全性更好控制
- 保持相同的 DoS 保护参数

#### `src/capability/tools/weather.ts`

- 直接移植 mock 数据，5 个城市

#### `src/capability/tools/file-read.ts`

**Python 原逻辑**：
- 沙盒化读取（allowed_root 默认 CWD）
- 拒绝符号链接、路径穿越
- 100KB 限制 + 截断

**TypeScript 实现要点**：
```typescript
import fs from 'fs'
import path from 'path'

export class FileReadTool extends BaseTool {
  async execute(params: Record<string, unknown>): Promise<string> {
    const filePath = path.resolve(params.path as string)
    // 检查路径是否在 allowed_root 内
    // 使用 fs.lstatSync() 检查符号链接
    // 使用 fs.readFileSync() 读取，限制 100KB
  }
}
```

#### `src/capability/tools/file-write.ts`

**Python 原逻辑**：
- 只能写入 `memory/data/` 目录
- 拒绝符号链接、路径穿越、前缀碰撞攻击
- 原子写入（temp file + fsync + rename）

**TypeScript 实现要点**：
```typescript
import fs from 'fs'
import os from 'os'
import path from 'path'

function atomicWrite(filePath: string, data: string): void {
  const dir = path.dirname(filePath)
  const tmpPath = path.join(dir, `.tmp-${crypto.randomUUID()}`)
  const fd = fs.openSync(tmpPath, 'w')
  fs.writeSync(fd, data)
  fs.fsyncSync(fd)
  fs.closeSync(fd)
  fs.renameSync(tmpPath, filePath)
}
```

#### `src/capability/tools/file-edit.ts`

- 与 file-write 相同的安全检查
- 文本替换 + 唯一匹配验证
- 原子写入

#### `src/capability/basics/` 模块

- `commands.ts`：静态命令列表，与 Python 版一致
- `logs.ts`：包装 `log/writer` 模块
- `memory-files.ts`：包装 MemoryProvider
- `sessions.ts`：包装 MemoryProvider

---

### 4.6 Memory 层

#### `src/memory/session.ts`

**Python 原逻辑**（最复杂的模块之一）：
- `SessionManager` 类：UUID session 文件 + index.json 索引
- fcntl 文件锁 -> TypeScript 使用 `proper-lockfile`
- 原子 JSON 写入 -> 同样的 temp file + fsync + rename 模式
- 索引损坏恢复：从 session 文件重建
- 陈旧条目清理
- 并发安全合并（base_count tracking）

**TypeScript 实现要点**：
```typescript
import lockfile from 'proper-lockfile'

export class SessionManager {
  private sessionsDir: string
  private indexPath: string

  constructor(dataDir: string) {
    this.sessionsDir = path.join(dataDir, 'sessions')
    this.indexPath = path.join(this.sessionsDir, 'index.json')
  }

  private async withIndexLock<T>(fn: () => Promise<T>): Promise<T> {
    const lockPath = path.join(this.sessionsDir, '.index.lock')
    fs.writeFileSync(lockPath, '')
    const release = await lockfile.lock(lockPath, { retries: 3, realpath: false })
    try {
      return await fn()
    } finally {
      await release()
    }
  }

  // ... 其他方法逻辑与 Python 版完全一致
}
```

**重要**：`proper-lockfile` 是异步的，所以所有锁操作需要 `async/await`。Python 版的同步 `fcntl.flock` 对应到 TypeScript 的 `await lockfile.lock()`。

#### `src/memory/soul.ts` 和 `src/memory/user.ts`

- 简单的文件读写（exists check, load, atomic save）
- 使用 `fs.existsSync()`, `fs.readFileSync()`, `atomicWrite()`

#### `src/memory/storage.ts`

**Python 原逻辑**：
- `MemoryStorage`：session 级别消息存储
- `add_message()` 追加 UTC 时间戳
- `save()` 委托给 SessionManager，带 base_count 并发安全
- 损坏文件隔离（rename to .corrupt）

**TypeScript 实现要点**：
- 逻辑完全一致
- 时间戳：`new Date().toISOString()`
- 损坏隔离：`fs.renameSync(corruptPath, corruptPath + '.corrupt')`

#### `src/memory/strategy.ts`

**Python 原逻辑**：
- `MemoryStrategy`：构建 system prompt + 管理上下文窗口
- `_ONBOARDING_TEMPLATE` 和 `_MEMORY_MGMT_TEMPLATE` 模板
- Token 计数：tiktoken (gpt-4 encoding) + char/4 fallback
- 上下文窗口：从后往前遍历 history，保留 system messages

**TypeScript 实现要点**：
```typescript
import { encodingForModel } from 'js-tiktoken'

export class MemoryStrategy {
  private encoder: ReturnType<typeof encodingForModel> | null

  constructor(private soulManager: SoulManager, private userManager: UserMemoryManager, maxTokens = 8000) {
    try {
      this.encoder = encodingForModel('gpt-4')
    } catch {
      this.encoder = null
    }
  }

  private countTokens(text: string): number {
    if (!text) return 0
    if (this.encoder) return this.encoder.encode(text).length
    return Math.max(1, Math.floor(text.length / 4))
  }
}
```

- 模板字符串直接移植（保持中文内容不变）
- data-guard 注入防护逻辑保持一致

#### `src/memory/provider.ts`

**Python 原逻辑**：
- `BrixMemoryProvider`：组合 SoulManager, UserMemoryManager, SessionManager, MemoryStorage, MemoryStrategy
- 懒 session 创建（首次 add_message 时才分配 UUID）
- 空 session 清理

**TypeScript 实现要点**：
- 实现 `MemoryProvider` 接口
- 所有管理器作为私有属性
- 懒创建逻辑完全一致

---

### 4.7 Log 层

#### `src/log/flow.ts`

**Python 原逻辑**：
- `FlowLog`：内存中步骤收集器
- 8 字符 hex trace ID
- `step(module, **kwargs)` 记录管道步骤
- `finish()` 返回 JSONL-ready dict

**TypeScript 实现要点**：
```typescript
export class FlowLog {
  private traceId: string
  private steps: Array<{ module: string; data: Record<string, unknown>; ts: number }> = []
  private startTime: number

  constructor(private input: string) {
    this.traceId = crypto.randomUUID().replace(/-/g, '').slice(0, 8)
    this.startTime = performance.now()
  }

  step(module: string, data: Record<string, unknown> = {}): void {
    this.steps.push({ module, data, ts: performance.now() })
  }
}
```

#### `src/log/writer.ts`

**Python 原逻辑**：
- JSONL 文件 I/O：`write_jsonl()`, `flush_log()`, `read_all()`, `read_entry()`, `format_detail()`

**TypeScript 实现要点**：
- `writeJsonl()`: `fs.appendFileSync(path, JSON.stringify(data) + '\n')`
- `readAll()`: `fs.readFileSync(path, 'utf-8').split('\n').filter(Boolean).map(JSON.parse)`
- `formatDetail()`: 计算步骤间耗时，渲染详情（保持中文描述）

---

### 4.8 Hook 层

#### `src/hooks/registry.ts`

**Python 原逻辑**：
- `HookRegistry`：`bind_log()`, `register()`, `fire()`
- 单个 hook 异常不影响其他 hook

**TypeScript 实现要点**：
```typescript
export class HookRegistry {
  private log: FlowLog | null = null
  private hooks: Map<string, Array<(event: HookEvent) => void | Promise<void>>> = new Map()

  bindLog(log: FlowLog): void { this.log = log }
  register(event: string, hook: (event: HookEvent) => void | Promise<void>): void { ... }
  async fire(event: string, data: Record<string, unknown> = {}): Promise<void> {
    // 先调用 log.step()
    // 再调用所有注册的 hook，单个异常不影响其他
  }
}
```

---

### 4.9 CLI 层

#### `src/cli/app.ts` — 主 REPL 类

**Python 原逻辑**：
- `BrixCLI` 类：初始化所有组件，REPL 循环，命令处理，流式处理管道
- 使用 `prompt_toolkit` 的 `PromptSession` + `FuzzyCompleter`

**TypeScript 实现要点**：

**REPL 方案选择**：使用 `@inquirer/prompts` 替代 `prompt_toolkit`

```typescript
import { input, select } from '@inquirer/prompts'
import chalk from 'chalk'

export class BrixCLI {
  private config: BrixConfig
  private memory: MemoryProvider
  private llmClient: LLMClient
  private toolRunner: ToolRunner
  private orchestrator: OrchestratorEngine

  constructor(config?: BrixConfig) {
    this.config = config ?? loadConfig()
    // ... 初始化所有组件
  }

  async run(): Promise<void> {
    showBanner(this.config, '0.1.0')
    while (true) {
      try {
        const userInput = await input({
          message: chalk.cyan.bold('  ❯ '),
        })
        // ... 处理输入
      } catch (e) {
        // EOF/Ctrl+C
        this.memory.saveSession()
        console.log('\nGoodbye.')
        break
      }
    }
  }
}
```

**注意**：`@inquirer/prompts` 的 `input()` 不支持 fuzzy completion。替代方案：
1. 使用 `readline` 原生接口 + 自定义 completer（推荐，最灵活）
2. 使用 `ink` + React 构建完整 TUI（参考项目方案，但复杂度高）

**推荐方案**：使用 Node.js `readline` + `chalk` + 自定义 slash 命令补全

```typescript
import * as readline from 'readline'

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  completer: (line: string) => {
    if (line.startsWith('/')) {
      const commands = ['/help', '/quit', '/clear', '/model', '/history', '/resume', '/soul', '/user', '/log']
      const hits = commands.filter(c => c.startsWith(line))
      return [hits.length ? hits : commands, line]
    }
    return [[], line]
  }
})
```

#### `src/cli/banner.ts`

- ASCII art + chalk 颜色
- 显示 model、version、cwd

#### `src/cli/completer.ts`

- slash 命令补全逻辑，集成到 readline completer

#### `src/cli/spinner.ts`

**Python 原逻辑**：
- Braille 动画帧，Rich Live + threading

**TypeScript 实现要点**：
```typescript
import ora from 'ora'
// 或者自实现：
const FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

export class Spinner {
  private timer: ReturnType<typeof setInterval> | null = null
  private frameIdx = 0
  private label = ''

  start(label: string): void {
    this.label = label
    this.timer = setInterval(() => {
      process.stdout.write(`\r${FRAMES[this.frameIdx++ % FRAMES.length]} ${this.label}`)
    }, 80)
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer)
      this.timer = null
      process.stdout.write('\r' + ' '.repeat(this.label.length + 4) + '\r')
    }
  }
}
```

#### `src/cli/stage_indicator.ts`

- 包装 Spinner，按阶段更新标签

#### `src/cli/stream_renderer.ts`

**Python 原逻辑**：
- 安全边界 Markdown 渲染（code fence 关闭后、空行后、非 fence 换行后）
- `_CompactMarkdown`：移除段落间空行
- `_MarkerMarkdown`：首行 marker + 后续行缩进
- 0.8s 空闲后显示 activity indicator

**TypeScript 实现要点**：
```typescript
import { marked } from 'marked'
import TerminalRenderer from 'marked-terminal'
import chalk from 'chalk'

marked.setOptions({ renderer: new TerminalRenderer() })

export class StreamRenderer {
  private pending = ''
  private rendered = ''
  private marker: string
  private lastDeltaTime = 0
  private activityTimer: ReturnType<typeof setTimeout> | null = null

  constructor(marker = chalk.green('  ⏺ ')) {
    this.marker = marker
  }

  pushDelta(delta: string): void {
    this.lastDeltaTime = Date.now()
    this.pending += delta
    const boundary = this.findSafeBoundary(this.pending)
    if (boundary !== null) {
      this.rendered += this.pending.slice(0, boundary)
      this.pending = this.pending.slice(boundary)
    }
    this.updateDisplay()
  }

  private findSafeBoundary(text: string): number | null {
    // 与 Python 版逻辑完全一致
  }
}
```

#### `src/cli/tool_display.ts`

- 工具执行面板：chalk 边框 + 工具特定格式
- 思考 spinner

#### `src/cli/theme.ts`

- 定义 chalk 样式常量（替代 Rich Theme）

#### `src/cli/display.ts`

- `formatResponse()`: 直通
- `renderHistory()`: 用 chalk 渲染消息历史

#### `src/cli/paginated-selector.ts`

**Python 原逻辑**：
- 泛型 TUI 分页选择器
- 键绑定：上下左右/home/end/enter/escape/数字
- prompt_toolkit Application

**TypeScript 实现要点**：
- 使用 `@inquirer/prompts` 的 `select()` 配合 `pageSize` 选项
- 或者自实现：监听 stdin keypress 事件 + 渲染

```typescript
import { select } from '@inquirer/prompts'

export async function paginatedSelect<T>(
  items: T[],
  formatItem: (item: T, idx: number) => string,
  pageSize = 10,
  title = 'Select',
): Promise<T | null> {
  const choices = items.map((item, idx) => ({
    name: formatItem(item, idx),
    value: item,
  }))
  try {
    return await select({ message: title, choices, pageSize })
  } catch {
    return null // User cancelled
  }
}
```

---

## 五、CLI 入口与 `brix` 命令注册

### 5.1 `src/entrypoints/cli.ts`

```typescript
#!/usr/bin/env bun
import 'dotenv/config'
import { BrixCLI } from '../cli/app.js'

async function main() {
  const cli = new BrixCLI()
  await cli.run()
}

main().catch(console.error)
```

### 5.2 `package.json` bin 配置

```json
{
  "name": "brix",
  "version": "0.1.0",
  "description": "Personal AI Agent",
  "type": "module",
  "bin": {
    "brix": "dist/cli.js"
  },
  "scripts": {
    "build": "bun build src/entrypoints/cli.ts --outfile dist/cli.js --target bun --banner '#!/usr/bin/env bun'",
    "dev": "bun run src/entrypoints/cli.ts",
    "test": "bun test",
    "typecheck": "tsc --noEmit",
    "lint": "biome check src/"
  }
}
```

### 5.3 从 Python alias 迁移

当前 `.zshrc` 第 459 行：
```bash
alias brix="cd ~/Applications/Brix && .venv/bin/python main.py"
```

**迁移步骤**：

1. **先改 alias 过渡**（立即可用）：
   ```bash
   # .zshrc 中替换为：
   alias brix="cd ~/Applications/Brix && bun run src/entrypoints/cli.ts"
   ```

2. **再用 `bun link` 注册为全局命令**（推荐最终方案）：
   ```bash
   cd ~/Applications/Brix
   bun link          # 根据 package.json 的 "bin.brix" 注册到 $PATH
   ```

3. **确认可用后删除 alias**：
   ```bash
   # 删除 .zshrc 中的 alias brix 那行
   # 新开终端，直接输入 brix 即可启动
   which brix        # 应输出 ~/.bun/bin/brix 或类似路径
   ```

**两种方式对比**：

| | alias | bun link |
|---|---|---|
| 需要 cd 到项目目录 | 是 | 否 |
| 需要 .zshrc 配置 | 是 | 否 |
| 真正的全局命令 | 否 | 是 |
| 换机器需要重新配 | 是 | `bun link` 一行搞定 |

---

## 六、测试迁移

### 6.1 测试框架

- **Vitest** 替代 pytest
- 测试文件：`tests/*.test.ts`
- 支持 async/await 测试

### 6.2 测试映射

| Python 测试文件 | TypeScript 测试文件 |
|----------------|-------------------|
| `test_config.py` | `tests/config.test.ts` |
| `test_infra.py` | `tests/infra.test.ts` |
| `test_router.py` | `tests/router.test.ts` |
| `test_orchestrator.py` | `tests/orchestrator.test.ts` |
| `test_langgraph.py` | `tests/langgraph.test.ts` (可选) |
| `test_capability.py` | `tests/capability.test.ts` |
| `test_file_tools.py` | `tests/file-tools.test.ts` |
| `test_memory.py` | `tests/memory.test.ts` |
| `test_memory_v2.py` | `tests/memory-v2.test.ts` |
| `test_flow_log.py` | `tests/flow-log.test.ts` |
| `test_hooks.py` | `tests/hooks.test.ts` |
| `test_cli.py` | `tests/cli.test.ts` |
| `test_completer.py` | `tests/completer.test.ts` |
| `test_stream_renderer.py` | `tests/stream-renderer.test.ts` |
| `test_stage_indicator.py` | `tests/stage-indicator.test.ts` |
| `test_tool_display.py` | `tests/tool-display.test.ts` |
| `test_paginated_selector.py` | `tests/paginated-selector.test.ts` |
| `test_streaming.py` | `tests/streaming.test.ts` |
| `test_basics.py` | `tests/basics.test.ts` |

### 6.3 Mock 策略

- `vi.fn()` / `vi.spyOn()` 替代 `unittest.mock.MagicMock`
- `vi.mock()` 替代 `unittest.mock.patch`
- 异步 mock：`vi.fn().mockResolvedValue(...)` 替代 `AsyncMock`

---

## 七、迁移执行顺序

### Phase 1: 项目骨架（Day 1）

1. 创建 `package.json`, `tsconfig.json`, `.gitignore` 更新
2. 创建 `src/` 目录结构
3. 安装依赖：`bun install`
4. 创建 `src/types.ts`（全局类型定义）
5. 创建 `src/entrypoints/cli.ts`（最小入口）
6. 验证 `bun run src/entrypoints/cli.ts` 可运行

### Phase 2: Config + Infra（Day 2-3）

1. `src/config/loader.ts` — YAML 配置加载
2. `src/config/model-registry.ts` — 模型注册表
3. `src/infra/providers/openai-compat.ts` — OpenAI provider
4. `src/infra/providers/anthropic-compat.ts` — Anthropic provider
5. `src/infra/llm-client.ts` — 统一 LLM 客户端
6. 测试：`tests/config.test.ts`, `tests/infra.test.ts`

### Phase 3: Memory 层（Day 4-5）

1. `src/memory/session.ts` — SessionManager（最复杂）
2. `src/memory/soul.ts` — SoulManager
3. `src/memory/user.ts` — UserMemoryManager
4. `src/memory/storage.ts` — MemoryStorage
5. `src/memory/strategy.ts` — MemoryStrategy
6. `src/memory/provider.ts` — BrixMemoryProvider
7. `src/memory/types.ts` — MemoryProvider 接口
8. 测试：`tests/memory.test.ts`, `tests/memory-v2.test.ts`

### Phase 4: Router + Orchestrator（Day 6）

1. `src/router/intent.ts`
2. `src/router/complexity.ts`
3. `src/router/model-router.ts`
4. `src/orchestrator/engine.ts` — 接口定义
5. `src/orchestrator/states.ts` — 状态枚举
6. `src/orchestrator/state-machine.ts` — 状态机编排器
7. 测试：`tests/router.test.ts`, `tests/orchestrator.test.ts`

### Phase 5: Capability 层（Day 7）

1. `src/capability/base.ts` — Tool 接口
2. `src/capability/runner.ts` — ToolRunner
3. `src/capability/tools/calculator.ts`
4. `src/capability/tools/weather.ts`
5. `src/capability/tools/file-read.ts`
6. `src/capability/tools/file-write.ts`
7. `src/capability/tools/file-edit.ts`
8. `src/capability/basics/` — commands, logs, memory-files, sessions
9. 测试：`tests/capability.test.ts`, `tests/file-tools.test.ts`

### Phase 6: Log + Hooks（Day 8）

1. `src/log/flow.ts`
2. `src/log/writer.ts`
3. `src/hooks/registry.ts`
4. 测试：`tests/flow-log.test.ts`, `tests/hooks.test.ts`

### Phase 7: CLI 层（Day 9-10）

1. `src/cli/theme.ts` — 样式常量
2. `src/cli/banner.ts` — Banner
3. `src/cli/spinner.ts` — Spinner
4. `src/cli/stage-indicator.ts` — StageIndicator
5. `src/cli/stream-renderer.ts` — StreamRenderer
6. `src/cli/tool-display.ts` — ToolDisplay
7. `src/cli/display.ts` — display 工具
8. `src/cli/completer.ts` — 补全器
9. `src/cli/paginated-selector.ts` — 分页选择器
10. `src/cli/app.ts` — 主 REPL 类（集成所有组件）
11. 测试：各 CLI 组件测试

### Phase 8: 集成与发布（Day 11）

1. 完整集成测试
2. `bun build` 打包
3. `bun link` 注册全局 `brix` 命令
4. 更新 `.zshrc`：先改 alias 过渡，确认 `bun link` 可用后删除 alias
5. 更新 README.md
6. 更新 CLAUDE.md
7. 清理 Python 文件（或保留为参考）

---

## 八、关键注意事项

### 8.1 必须完全移植的行为

1. **Anthropic 消息格式转换**：system 提取、tool_use/tool_result 块转换
2. **文件锁机制**：所有 index.json 和 session 文件操作必须有锁保护
3. **原子写入**：temp file + fsync + rename 模式
4. **Session 并发安全**：base_count tracking + 合并逻辑
5. **索引损坏恢复**：从 session 文件重建索引
6. **上下文窗口**：token 计数 + 从后往前遍历 + system 消息保留
7. **System prompt 构建**：soul (no data-guard) + user (with data-guard) + onboarding/memory-mgmt 模板
8. **Calculator DoS 保护**：max depth, max nodes, exponent cap
9. **文件工具安全**：路径穿越检查、符号链接拒绝、沙盒限制
10. **流式事件格式**：text_delta, tool_call, tool_result 事件类型必须一致

### 8.2 可以简化的部分

1. **LangGraph 引擎**：第一阶段可跳过，只保留 StateMachineOrchestrator
2. **`@runtime_checkable`**：TypeScript 接口天然在编译时检查，无需运行时检查
3. **`fcntl` 锁**：`proper-lockfile` 是更高层的抽象，内部处理了跨平台差异

### 8.3 数据文件兼容性

- `src/config/settings.yaml` — 保持不变，TypeScript 用 `js-yaml` 解析
- `src/memory/data/soul.md`, `user.md` — 保持不变（路径从 `memory/data/` 变为 `src/memory/data/`）
- `src/memory/data/sessions/index.json` — 格式保持不变，TypeScript 读写兼容
- `src/memory/data/sessions/session-*.json` — 格式保持不变
- `src/log/data/brix.jsonl` — 格式保持不变

> **注意**：如果迁移时希望保留已有会话数据，需要将 `memory/data/` 下的文件复制到 `src/memory/data/`，将 `log/data/` 下的文件复制到 `src/log/data/`。

### 8.4 配置文件保持不变

- `.env` — 保持不变，用 `dotenv` 加载
- `.env.example` — 保持不变
- `.gitignore` — 更新，添加 `node_modules/`, `dist/`, `src/memory/data/`, `src/log/data/`

---

## 九、`tsconfig.json` 参考配置

```json
{
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "outDir": "./dist",
    "rootDir": "./src",
    "baseUrl": ".",
    "paths": {
      "src/*": ["./src/*"]
    }
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

---

## 十、`package.json` 参考配置

```json
{
  "name": "brix",
  "version": "0.1.0",
  "description": "Personal AI Agent",
  "type": "module",
  "bin": {
    "brix": "dist/cli.js"
  },
  "scripts": {
    "build": "bun build src/entrypoints/cli.ts --outfile dist/cli.js --target bun --banner '#!/usr/bin/env bun'",
    "dev": "bun run src/entrypoints/cli.ts",
    "test": "bun test",
    "typecheck": "tsc --noEmit",
    "lint": "biome check src/",
    "format": "biome format src/"
  },
  "dependencies": {
    "@anthropic-ai/sdk": "^0.39.0",
    "chalk": "^5.4.0",
    "dotenv": "^16.5.0",
    "js-yaml": "^4.1.0",
    "js-tiktoken": "^1.0.0",
    "marked": "^15.0.0",
    "marked-terminal": "^7.0.0",
    "openai": "^4.0.0",
    "ora": "^8.0.0",
    "proper-lockfile": "^4.1.0"
  },
  "devDependencies": {
    "@biomejs/biome": "^1.9.0",
    "@types/js-yaml": "^4.0.0",
    "@types/proper-lockfile": "^4.1.0",
    "typescript": "^5.7.0",
    "vitest": "^3.0.0"
  },
  "engines": {
    "bun": ">=1.3.0"
  }
}
```

---

## 十一、`.gitignore` 更新

```gitignore
# 新增
node_modules/
dist/
*.js.map
*.d.ts

# 保留（路径更新）
.env
src/memory/data/
src/log/data/
*.pyc
__pycache__/
.venv/
```

---

## 十二、CLAUDE.md 更新

迁移完成后需要更新 `CLAUDE.md` 中的开发约束：

```markdown
# Brix 开发约束

## 模块化（最高优先级）

所有层通过 TypeScript 接口通信，禁止跨层直接 import 内部实现。

- `cli/` → 依赖各层的接口定义，不 import 内部实现
- `orchestrator/` → 通过 `OrchestratorEngine` 接口
- `memory/` → 通过 `MemoryProvider` 接口
- `capability/` → 通过 `Tool` 接口 + `ToolRunner`
- `router/` → 通过函数调用（classifyIntent, selectModel）
- `infra/` → 通过 `LLMClient` 类

替换任何一层只需满足同一接口，不改动调用方。

## 数据与逻辑分离

运行时数据放各模块的 `data/` 子目录（如 `src/memory/data/`、`src/log/data/`），`.ts` 是逻辑层，`.md`/`.json` 是数据层。各 `data/` 目录加入 `.gitignore`。

## 代码风格

- 中文注释和文档
- TypeScript strict 模式
- 异步优先 (async/await)，fail gracefully
- 文件名使用 kebab-case
- 类型定义优先使用 `type` 而非 `interface`（与参考项目一致，但 Protocol 用 `interface`）
```

---

## 十三、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| `proper-lockfile` 在 macOS/Linux 行为不一致 | 并发安全 | 测试覆盖，并发场景专项测试 |
| `js-tiktoken` 与 Python tiktoken 结果微差 | token 计数不精确 | 差异极小（<1%），可接受 |
| `marked-terminal` 渲染效果与 Rich Markdown 不同 | 终端显示差异 | 对比调整，必要时自定义 renderer |
| `@inquirer/prompts` 不支持 fuzzy completion | REPL 体验降级 | 使用 readline 原生 completer |
| Bun 生态不如 Node.js 成熟 | 依赖兼容性 | 核心依赖（openai, anthropic, chalk）均兼容 Bun |
| Anthropic SDK TypeScript 版与 Python 版 API 差异 | 消息格式转换逻辑 | 仔细对照 Python 实现，测试覆盖 |

---

## 十四、验收标准

迁移完成的标志：

1. `bun run src/entrypoints/cli.ts` 或 `brix` 命令可正常启动 REPL
2. 所有 9 个 slash 命令正常工作（/help, /quit, /clear, /model, /history, /resume, /soul, /user, /log）
3. 流式对话正常（text_delta, tool_call, tool_result 事件）
4. 工具调用正常（calculator, weather, file_read, file_write, file_edit）
5. Memory 正常（session 创建/恢复/列表、soul.md、user.md）
6. Router 正常（intent 分类、complexity 评估、model 选择）
7. Log 正常（FlowLog + JSONL 写入/读取）
8. 所有数据文件与 Python 版兼容（可互相读取）
9. `bun test` 全部通过
10. `tsc --noEmit` 无类型错误
