# Brix Python -> TypeScript 完整迁移设计

**日期:** 2026-05-11
**状态:** Draft

## 目标

将 Brix 从 Python 3.11+ 全面迁移至 TypeScript，保持当前分层架构（Protocol 接口隔离）和所有已实现功能不变。迁移后 CLI 入口为终端输入 `brix` 即可启动。

## 架构

### 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| **运行时** | Bun (>=1.3.0) | 启动快、原生 TS、与参考项目一致 |
| **模块系统** | ESM (`"type": "module"`) | 原生 async/await、现代标准 |
| **TypeScript** | strict: true, target: ESNext | 类型安全、最新特性 |
| **构建** | Bun.build() → `dist/cli.js` | 单文件打包、shebang 支持 |
| **测试** | Vitest | 快速、ESM 原生、与 Bun 兼容 |
| **Lint** | Biome | 参考项目惯例、速度快 |

### 依赖映射

| Python 依赖 | TypeScript 替代 | 用途 |
|-------------|----------------|------|
| `pyyaml` | `js-yaml` + `@types/js-yaml` | YAML 配置解析 |
| `openai` | `openai` (npm) | OpenAI 兼容 API |
| `anthropic` | `@anthropic-ai/sdk` (npm) | Anthropic API |
| `prompt-toolkit` | `readline` + `chalk` | REPL 交互、颜色 |
| `rich` | `chalk` + `marked` + `marked-terminal` | 终端 UI |
| `tiktoken` | `js-tiktoken` | Token 计数 |
| `tenacity` | 自实现 `retry()` | 重试逻辑 |
| `python-dotenv` | `dotenv` (npm) | .env 加载 |
| `fcntl` | `proper-lockfile` | 文件锁 |
| `uuid` | `crypto.randomUUID()` | UUID 生成 |

### 目录结构

```
Brix/
├── src/                           # 所有源码
│   ├── types.ts                   # 全局类型定义
│   ├── config/                    # 配置层
│   │   ├── loader.ts
│   │   ├── model-registry.ts
│   │   └── settings.yaml
│   ├── infra/                     # 基础设施层
│   │   ├── llm-client.ts
│   │   └── providers/
│   │       ├── openai-compat.ts
│   │       └── anthropic-compat.ts
│   ├── router/                    # 路由层
│   │   ├── intent.ts
│   │   ├── complexity.ts
│   │   └── model-router.ts
│   ├── orchestrator/              # 编排层
│   │   ├── engine.ts
│   │   ├── states.ts
│   │   └── state-machine.ts
│   ├── capability/                # 工具层
│   │   ├── base.ts
│   │   ├── runner.ts
│   │   ├── basics/
│   │   └── tools/
│   ├── memory/                    # 记忆层
│   │   ├── types.ts
│   │   ├── provider.ts
│   │   ├── session.ts
│   │   ├── soul.ts
│   │   ├── user.ts
│   │   ├── storage.ts
│   │   ├── strategy.ts
│   │   └── data/                  # 运行时数据
│   ├── log/                       # 日志层
│   │   ├── flow.ts
│   │   ├── writer.ts
│   │   └── data/
│   ├── hooks/                     # 钩子层
│   │   └── registry.ts
│   ├── cli/                       # 界面层
│   │   ├── app.ts
│   │   ├── banner.ts
│   │   ├── completer.ts
│   │   ├── display.ts
│   │   ├── paginated-selector.ts
│   │   ├── spinner.ts
│   │   ├── stage-indicator.ts
│   │   ├── stream-renderer.ts
│   │   ├── theme.ts
│   │   └── tool-display.ts
│   └── entrypoints/
│       └── cli.ts                 # 入口文件
├── tests/                         # 测试文件
├── package.json
├── tsconfig.json
├── .gitignore
└── CLAUDE.md
```

## 组件

### 核心类型定义

```typescript
// src/types.ts
export type Message = {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  tool_calls?: ToolCallData[]
  tool_call_id?: string
  tool_name?: string
  timestamp?: string
}

export type ToolCallData = {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export type LLMResponse = {
  content: string
  tool_calls: ToolCallData[]
  finish_reason: string
}

export type StreamEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'tool_call'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; id: string; name: string; result: string; ms: number; is_error: boolean }
```

### MemoryProvider 接口

```typescript
// src/memory/types.ts
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

### OrchestratorEngine 接口

```typescript
// src/orchestrator/engine.ts
export interface ToolRunner {
  run(toolName: string, params: Record<string, unknown>): Promise<string>
  getToolSchemas(): Record<string, unknown>[]
}

export interface OrchestratorEngine {
  run(userInput: string, context: OrchestratorContext): Promise<string>
  runStream(userInput: string, context: OrchestratorContext): AsyncGenerator<StreamEvent>
}
```

### Tool 接口

```typescript
// src/capability/base.ts
export interface Tool {
  readonly name: string
  readonly description: string
  readonly inputSchema: Record<string, unknown>
  execute(params: Record<string, unknown>): Promise<string>
  toOpenAiSchema(): Record<string, unknown>
}
```

## 数据流

```
用户输入
    ↓
CLI (app.ts)
    ↓
Router (intent.ts, complexity.ts, model-router.ts)
    ↓
Orchestrator (state-machine.ts)
    ↓
LLMClient (llm-client.ts)
    ↓
Provider (openai-compat.ts / anthropic-compat.ts)
    ↓
ToolRunner (runner.ts)
    ↓
Tool (calculator.ts, file-read.ts, etc.)
    ↓
MemoryProvider (provider.ts)
    ↓
CLI 输出 (stream-renderer.ts, tool-display.ts)
```

## 错误处理

### LLM 调用重试

```typescript
async function retry<T>(
  fn: () => Promise<T>,
  options: {
    retries: number
    baseDelay: number
    maxDelay: number
    isRetryable: (e: unknown) => boolean
  }
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

### 可重试错误类型

- `RateLimitError`
- `APITimeoutError`
- `APIConnectionError`
- `InternalServerError`
- 5xx 状态码

### 文件操作安全

- 路径穿越检查：`path.resolve()` + `is_relative_to()`
- 符号链接拒绝：`fs.lstatSync()`
- 原子写入：temp file + fsync + rename
- 文件锁：`proper-lockfile`

## 测试策略

### 测试框架

- **Vitest**：快速、ESM 原生、与 Bun 兼容
- 测试文件：`tests/*.test.ts`
- Mock：`vi.fn()` / `vi.spyOn()` / `vi.mock()`

### 测试覆盖

| Phase | 测试文件 | 覆盖内容 |
|-------|---------|---------|
| Phase 1 | `config.test.ts`, `infra.test.ts` | 配置加载、LLM 调用 |
| Phase 2 | `memory.test.ts`, `flow-log.test.ts`, `hooks.test.ts` | 会话管理、日志、钩子 |
| Phase 3 | `router.test.ts`, `orchestrator.test.ts`, `capability.test.ts`, `file-tools.test.ts` | 路由、编排、工具 |
| Phase 4 | `cli.test.ts` | CLI 集成 |

### 数据兼容性

- 所有数据文件格式保持不变（JSON, Markdown, JSONL）
- TypeScript 代码按照相同格式读写
- 迁移时复制现有数据文件到新目录结构

## 执行计划

### Phase 1：项目骨架 + Config + Infra + Types（第 1 周）

**目标**：建立 TypeScript 项目基础，完成配置和基础设施层迁移

| 任务 | 内容 | 验收标准 |
|------|------|---------|
| 1.1 | 创建 `package.json`, `tsconfig.json` | `bun install` 成功 |
| 1.2 | 创建 `src/types.ts` 全局类型 | 类型定义完整 |
| 1.3 | 迁移 `config/loader.ts` | 配置加载正常 |
| 1.4 | 迁移 `config/model-registry.ts` | 模型查询正常 |
| 1.5 | 迁移 `infra/providers/openai-compat.ts` | OpenAI 调用正常 |
| 1.6 | 迁移 `infra/providers/anthropic-compat.ts` | Anthropic 调用正常 |
| 1.7 | 迁移 `infra/llm-client.ts` | 统一调用正常 |
| 1.8 | 迁移 `config/settings.yaml` | 配置文件兼容 |
| 1.9 | 编写测试：`tests/config.test.ts` | 测试通过 |
| 1.10 | 编写测试：`tests/infra.test.ts` | 测试通过 |

### Phase 2：Memory + Log + Hooks（第 2 周）

**目标**：完成数据持久化和事件系统迁移

| 任务 | 内容 | 验收标准 |
|------|------|---------|
| 2.1 | 迁移 `memory/session.ts` | Session CRUD 正常 |
| 2.2 | 迁移 `memory/soul.ts` | Soul 读取正常 |
| 2.3 | 迁移 `memory/user.ts` | User 读取正常 |
| 2.4 | 迁移 `memory/storage.ts` | 消息存储正常 |
| 2.5 | 迁移 `memory/strategy.ts` | 上下文窗口正常 |
| 2.6 | 迁移 `memory/provider.ts` | MemoryProvider 完整 |
| 2.7 | 迁移 `log/flow.ts` | FlowLog 正常 |
| 2.8 | 迁移 `log/writer.ts` | JSONL 读写正常 |
| 2.9 | 迁移 `hooks/registry.ts` | Hook 注册/触发正常 |
| 2.10 | 迁移数据文件结构 | data/ 目录兼容 |
| 2.11 | 编写测试：`tests/memory.test.ts` | 测试通过 |
| 2.12 | 编写测试：`tests/flow-log.test.ts` | 测试通过 |
| 2.13 | 编写测试：`tests/hooks.test.ts` | 测试通过 |

### Phase 3：Router + Orchestrator + Capability（第 3 周）

**目标**：完成业务逻辑层迁移

| 任务 | 内容 | 验收标准 |
|------|------|---------|
| 3.1 | 迁移 `router/intent.ts` | 意图分类正常 |
| 3.2 | 迁移 `router/complexity.ts` | 复杂度评估正常 |
| 3.3 | 迁移 `router/model-router.ts` | 模型选择正常 |
| 3.4 | 迁移 `orchestrator/engine.ts` | 接口定义完整 |
| 3.5 | 迁移 `orchestrator/states.ts` | 状态枚举完整 |
| 3.6 | 迁移 `orchestrator/state-machine.ts` | 编排逻辑正常 |
| 3.7 | 迁移 `capability/base.ts` | Tool 接口完整 |
| 3.8 | 迁移 `capability/runner.ts` | ToolRunner 正常 |
| 3.9 | 迁移 `capability/tools/calculator.ts` | 计算器正常（含 DoS 保护） |
| 3.10 | 迁移 `capability/tools/weather.ts` | 天气工具正常 |
| 3.11 | 迁移 `capability/tools/file-read.ts` | 文件读取正常（含沙盒） |
| 3.12 | 迁移 `capability/tools/file-write.ts` | 文件写入正常（含原子写入） |
| 3.13 | 迁移 `capability/tools/file-edit.ts` | 文件编辑正常 |
| 3.14 | 迁移 `capability/basics/` | 基础命令正常 |
| 3.15 | 编写测试：`tests/router.test.ts` | 测试通过 |
| 3.16 | 编写测试：`tests/orchestrator.test.ts` | 测试通过 |
| 3.17 | 编写测试：`tests/capability.test.ts` | 测试通过 |
| 3.18 | 编写测试：`tests/file-tools.test.ts` | 测试通过 |

### Phase 4：CLI + 集成测试 + 发布（第 4 周）

**目标**：完成界面层迁移，集成测试，发布可用版本

| 任务 | 内容 | 验收标准 |
|------|------|---------|
| 4.1 | 迁移 `cli/theme.ts` | 样式定义完整 |
| 4.2 | 迁移 `cli/banner.ts` | Banner 显示正常 |
| 4.3 | 迁移 `cli/spinner.ts` | Spinner 动画正常 |
| 4.4 | 迁移 `cli/stage-indicator.ts` | 阶段指示正常 |
| 4.5 | 迁移 `cli/stream-renderer.ts` | 流式渲染正常 |
| 4.6 | 迁移 `cli/tool-display.ts` | 工具显示正常 |
| 4.7 | 迁移 `cli/display.ts` | 显示工具正常 |
| 4.8 | 迁移 `cli/completer.ts` | 命令补全正常 |
| 4.9 | 迁移 `cli/paginated-selector.ts` | 分页选择正常 |
| 4.10 | 迁移 `cli/app.ts` | REPL 正常 |
| 4.11 | 创建 `src/entrypoints/cli.ts` | 入口文件正常 |
| 4.12 | 配置 `package.json` bin | `brix` 命令可用 |
| 4.13 | 配置 `bun link` | 全局命令可用 |
| 4.14 | 更新 `.gitignore` | 忽略规则正确 |
| 4.15 | 更新 `CLAUDE.md` | 开发约束更新 |
| 4.16 | 编写测试：`tests/cli.test.ts` | 测试通过 |
| 4.17 | 集成测试 | 全功能正常 |
| 4.18 | 更新 README | 文档更新 |

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Anthropic 消息格式转换复杂 | 功能异常 | 仔细对照 Python 实现，测试覆盖 |
| `proper-lockfile` 跨平台差异 | 并发安全 | 测试覆盖，并发场景专项测试 |
| `js-tiktoken` 与 Python tiktoken 微差 | token 计数不精确 | 差异极小（<1%），可接受 |
| `marked-terminal` 渲染效果差异 | 终端显示差异 | 对比调整，必要时自定义 renderer |
| Calculator DoS 保护实现 | 安全风险 | 手写递归下降解析器，保持相同保护参数 |
| 文件工具安全检查 | 安全风险 | 仔细实现路径穿越检查、符号链接拒绝 |
| Bun 生态兼容性 | 依赖问题 | 核心依赖均兼容 Bun，遇到问题时寻找替代方案 |
| REPL 方案限制 | 用户体验 | 使用 readline 原生接口替代 @inquirer/prompts |

## 验收标准

迁移完成的标志：

1. **CLI 启动**：`bun run src/entrypoints/cli.ts` 或 `brix` 命令可正常启动 REPL，显示 Banner，提示符可输入
2. **Slash 命令**：所有 9 个 slash 命令正常工作
   - `/help`：显示帮助信息
   - `/quit`：退出 REPL
   - `/clear`：清空当前会话，创建新 session
   - `/model`：显示/切换当前模型
   - `/history`：显示消息历史
   - `/resume`：显示会话列表，可选择恢复
   - `/soul`：显示 soul.md 内容
   - `/user`：显示 user.md 内容
   - `/log`：显示 FlowLog 日志
3. **流式对话**：发送消息后，AI 响应实时流式显示（text_delta 事件），工具调用时显示 tool_call 和 tool_result 事件
4. **工具调用**：
   - `calculator`：计算表达式，支持 +, -, *, /, %, **，DoS 保护生效
   - `weather`：返回模拟天气数据
   - `file_read`：读取指定文件，沙盒限制生效（拒绝路径穿越、符号链接）
   - `file_write`：写入文件到 memory/data/，原子写入生效
   - `file_edit`：编辑文件，唯一匹配验证生效
5. **Memory 系统**：
   - `createSession()`：创建新 session，生成 UUID
   - `addMessage()`：追加消息，带 UTC 时间戳
   - `saveSession()`：保存到 JSON 文件
   - `loadSession()`/`resumeSession()`：加载历史 session
   - `listSessions()`：返回 session 列表
   - `loadSoul()`/`loadUserMemory()`：读取 md 文件
6. **Router**：
   - `classify_intent()`：LLM 分类 + 关键词回退
   - `evaluate_complexity()`：基于词数和关键词评估
   - `select_model()`：根据 intent 和 complexity 选择模型
7. **Log**：
   - `FlowLog`：记录步骤，生成 8 字符 hex trace ID
   - `writeJsonl()`：追加 JSONL 记录
   - `readAll()`/`readEntry()`：读取日志
8. **数据兼容**：所有数据文件格式与 Python 版完全一致（JSON, Markdown, JSONL），可互相读取
9. **测试通过**：`bun test` 全部通过，无失败用例
10. **类型检查**：`tsc --noEmit` 无类型错误

## 范围外

- LangGraph 引擎迁移（第一阶段只保留 StateMachineOrchestrator）
- Python 代码清理（可保留为参考）
- 性能优化（先保证功能正确）
- 新功能开发（迁移完成后再考虑）
