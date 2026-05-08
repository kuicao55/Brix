# Personal AI Agent Brix 架构设计文档（最终优化版）

> 名称：Brix（直接取自 Brick（砖块/积木） 的变体，复数形式暗示由多个组件堆叠而成）
> 口号：“Snap your capabilities together”
> 目标：构建一个可扩展、可替换、多入口、成本可控、可演进的个人 AI Agent 系统。  
> 本文档在保留原有分层思想的基础上，补充了模型路由、模型注册、LLM 基础设施层与完整调用链，形成可直接落地的工程方案。

---

## 1. 设计目标

构建一个长期可维护的个人 AI Agent 系统，满足以下要求：

- 多端入口一致：CLI / Desktop / Mobile / Voice 均可复用同一套核心能力
- 能力层独立：脱离 AI 也能运行，工具能力不依赖模型框架
- 路由清晰：能根据任务意图、复杂度、上下文长度、成本要求选择合适路径
- 模型可切换：支持多模型并存、模型热切换、fallback 与多模型协作
- 长期演进：未来可以平滑扩展为多 Agent、自动化工作流、任务调度系统
- 成本可控：简单任务使用低成本模型，复杂任务才使用强模型
- 可观测与可维护：便于日志、追踪、重试、限流、权限控制、审计

---

## 2. 总体架构

### 2.1 高层架构图

```text
┌──────────────────────────────────────────┐
│              Interface Layer             │
│   CLI / Desktop / Mobile / Voice / API   │
└───────────────────┬──────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│           Intent / Router Layer          │
│  意图识别 / 复杂度判断 / 路由决策 / 选模   │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │ Intent Classifier（意图识别）      │  │
│  │ Complexity Evaluator（复杂度判断） │  │
│  │ Model Router（模型路由）           │  │
│  │ Route Decision（执行路径选择）     │  │
│  └────────────────────────────────────┘  │
└───────────────────┬──────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│            Orchestrator Layer            │
│       Agent / Workflow / Planning        │
└───────────────────┬──────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│            Capability Layer ⭐           │
│  Tools / Wrappers / Runner / State       │
└───────────────────┬──────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│              Memory Layer                │
│   Storage / Retrieval / Strategy         │
└──────────────────────────────────────────┘

                    ↑
┌──────────────────────────────────────────┐
│               Infra Layer                │
│   LLM Client / Provider Adapters         │
└──────────────────────────────────────────┘

                    ↑
┌──────────────────────────────────────────┐
│               Config Layer               │
│   Model Registry / Routing Rules / Env   │
└──────────────────────────────────────────┘
```

### 2.2 架构原则

- 路由决定“走哪条路”
- 编排决定“怎么完成任务”
- 能力层决定“如何执行”
- 基础设施层决定“如何调用模型”
- 配置层决定“系统里有哪些模型，以及它们各自适合什么”

---

## 3. 分层说明

## 3.1 Interface Layer（接口层）

### 作用

负责所有用户入口和展示，不承载业务逻辑。

### 典型入口

- CLI
- Desktop（Electron / Tauri）
- Mobile
- Voice
- Web API

### 职责边界

- 接收用户输入
- 展示结果
- 传递给 Router
- 不直接调用工具
- 不包含模型选择逻辑
- 不处理业务编排

### 设计要求

接口层应当足够薄，避免出现“不同入口各自实现一套逻辑”的问题。所有入口最终都应该进入同一套 Router / Orchestrator / Capability 流程。

---

## 3.2 Intent / Router Layer（意图与路由层）

### 作用

负责理解用户想做什么，并决定后续执行路径。

### 核心职责

- 意图识别
- 复杂度判断
- 决定 direct 还是 agent
- 决定是否需要调用模型
- 决定使用哪个模型
- 决定是否进入 Orchestrator

### 建议输出结构

```json
{
  "intent": "chat | task | music | weather | coding | analysis",
  "route": "direct | agent",
  "complexity": "low | medium | high",
  "model": "gpt-4.1-mini",
  "requires_tools": true
}
```

### 内部模块

```text
Router Layer
 ├── Intent Classifier
 ├── Complexity Evaluator
 ├── Model Router
 └── Route Decision Engine
```

### 3.2.1 Intent Classifier（意图识别）

识别用户输入属于哪类任务，例如：

- 闲聊
- 问答
- 代码生成
- 总结
- 搜索
- 计划
- 多步骤任务
- 工具执行任务

### 3.2.2 Complexity Evaluator（复杂度判断）

根据以下因素判断任务复杂度：

- 文本长度
- 是否需要多轮推理
- 是否需要工具调用
- 是否涉及长上下文
- 是否有明确目标
- 是否有高准确率要求

### 3.2.3 Model Router（模型路由）

模型路由是 Router Layer 的一部分，但应独立成组件。

它的职责不是发请求，而是基于任务特征选择模型。

典型输入：

```json
{
  "intent": "coding",
  "complexity": "high",
  "needs_tool_calling": true,
  "needs_long_context": false,
  "budget_sensitive": false,
  "latency_sensitive": true
}
```

典型输出：

```json
{
  "model_id": "gpt-4.1",
  "provider": "openai"
}
```

### 3.2.4 路由策略示例

- 简单问答：低成本快模型
- 长文本总结：长上下文模型
- 复杂推理：高推理模型
- 工具调用：支持 function/tool calling 的模型
- 代码任务：代码能力强的模型
- 成本敏感：优先低成本模型
- 高精度：优先强模型

### 职责边界

Router Layer 只负责决策，不负责执行。

禁止把以下内容塞进 Router：

- 具体工具调用细节
- 重试、超时、日志
- 厂商 API 细节
- 复杂的多步工作流执行

---

## 3.3 Orchestrator Layer（编排层）

### 作用

负责“任务如何完成”，重点处理多步骤任务、工具调用、子任务拆分和状态推进。

### 核心职责

- 多步推理
- 工作流编排
- 任务拆分
- 工具调用决策
- 记忆读写协调
- 子任务执行
- 规划与回收

### 典型场景

- “帮我规划今晚的音乐播放”
- “把这个长文档总结成会议纪要”
- “根据我的偏好和历史记录推荐方案”
- “先查资料再生成最终答案”

### Orchestrator 内部可包含

- Planner
- Executor
- Replanner
- Tool Decision Node
- Memory Read/Write Node

### 模型协作方式

Orchestrator 可以复用 ModelRouter：

- 规划阶段：使用强推理模型
- 子任务阶段：使用快速模型
- 关键决策：使用高精度模型
- 大规模总结：使用长上下文模型

### 职责边界

Orchestrator 只负责“编排”，不直接承担底层执行责任。

不建议它直接做：

- HTTP 请求细节
- Provider 适配
- 工具内部实现
- 配置文件读取逻辑
- 密钥管理

---

## 3.4 Capability Layer（能力层）

### 作用

这是系统真正的执行核心，负责所有与现实世界交互的能力。

### 设计原则

- 与 Agent 框架解耦
- 可独立运行
- 能被 CLI 直接调用
- 不依赖模型
- 不依赖 Orchestrator

### 内部结构

```text
Capability Layer
 ├── Tools（原子能力）
 ├── Wrappers（横切逻辑）
 ├── Tool Runner（统一入口）
 └── State Provider（状态管理）
```

### 3.4.1 Tools（原子能力）

原子能力是最小可执行单元，例如：

- 播放音乐
- 搜索
- TTS
- 天气查询
- 文件操作
- 日历操作
- 邮件操作
- 本地脚本执行

### 工具定义建议

```ts
type Tool = {
  name: string
  inputSchema: JSONSchema
  execute: (params) => Promise<any>
}
```

### 3.4.2 Wrappers（横切逻辑）

统一处理：

- retry
- logging
- timeout
- fallback
- 并发控制
- 权限控制
- metrics

### 3.4.3 Tool Runner（统一入口）

统一调度所有工具：

```text
toolRunner.run("playMusic", params)
```

### 3.4.4 State Provider（状态管理）

管理有状态能力，例如：

- 当前播放状态
- 会话状态
- 任务执行状态
- 临时上下文状态

### 职责边界

Capability Layer 只关心执行，不关心模型。

---

## 3.5 Memory Layer（记忆层）

### 作用

负责短期记忆、长期记忆和检索策略。

### 结构

```text
Memory Layer
 ├── Storage
 ├── Retrieval
 └── Strategy
```

### 3.5.1 Storage

用于保存：

- 用户偏好
- 历史行为
- 任务结果
- 事件记录
- 会话状态

### 3.5.2 Retrieval

用于查找相关信息：

- embedding 搜索
- keyword 搜索
- 标签搜索
- 时间范围检索

### 3.5.3 Strategy

决定：

- 什么内容需要写入
- 什么时候写入
- 什么时候读取
- 读取多少
- 何时更新或失效

### 职责边界

Memory Layer 负责存储和检索，不负责业务逻辑和工具执行。

---

## 3.6 Infra Layer（基础设施层）

### 作用

统一管理所有模型调用，屏蔽不同供应商之间的差异。

### 结构

```text
infra/llm/
 ├── client.py
 ├── providers/
 │   ├── openai.py
 │   ├── anthropic.py
 │   ├── gemini.py
 │   └── local.py
 └── adapter.py
```

### 核心职责

- 统一 LLM 调用入口
- 屏蔽 provider 差异
- 处理重试、超时、流式输出
- 支持 fallback
- 支持工具调用参数转换
- 支持统一的请求与响应格式

### 为什么要单独拆出 Infra 层

因为模型调用不是业务能力，也不是工具能力，而是基础设施能力。  
这层的存在可以避免：

- Router 直接写 API 调用代码
- Orchestrator 直接依赖各厂商 SDK
- 业务代码到处散落 provider 差异处理

---

## 3.7 Config Layer（配置层）

### 作用

描述“系统拥有哪些模型、这些模型适合做什么、如何路由、如何连接 provider”。

### 文件结构建议

```text
config/
 ├── model_registry.yaml
 ├── routing_rules.yaml
 └── prompts/
```

### 3.7.1 模型注册表

模型注册表不负责决策，它只保存模型元数据。

#### 示例

```yaml
providers:
  openai:
    api_base: "https://api.openai.com/v1"
    api_key_env: "OPENAI_API_KEY"

  anthropic:
    api_base: "https://api.anthropic.com"
    api_key_env: "ANTHROPIC_API_KEY"

models:
  - id: "gpt-4.1-mini"
    provider: "openai"
    purpose:
      - "fast_chat"
      - "simple_qa"
      - "summarization"
    capabilities:
      - "low_latency"
      - "low_cost"
      - "tool_calling"
    max_context: 128000
    cost_tier: "low"
    default: true

  - id: "gpt-4.1"
    provider: "openai"
    purpose:
      - "coding"
      - "reasoning"
      - "planning"
      - "tool_use"
    capabilities:
      - "strong_reasoning"
      - "tool_calling"
      - "long_context"
    max_context: 128000
    cost_tier: "high"

  - id: "claude-3-7-sonnet"
    provider: "anthropic"
    purpose:
      - "analysis"
      - "coding"
      - "planning"
      - "long_context"
    capabilities:
      - "strong_reasoning"
      - "tool_calling"
      - "long_context"
    max_context: 200000
    cost_tier: "high"

routing:
  default_model: "gpt-4.1-mini"
  fallback_model: "gpt-4.1-mini"
```

### 3.7.2 routing_rules.yaml

用于表达更明确的路由规则，例如：

```yaml
rules:
  - when:
      intent: "simple_qa"
    use: "gpt-4.1-mini"

  - when:
      intent: "coding"
      complexity: "high"
    use: "gpt-4.1"

  - when:
      needs_long_context: true
    use: "claude-3-7-sonnet"
```

### 3.7.3 密钥管理

密钥不要写入配置文件，应使用环境变量：

```env
OPENAI_API_KEY=xxx
ANTHROPIC_API_KEY=xxx
GOOGLE_API_KEY=xxx
```

### 配置层原则

- 配置只描述能力，不做决策
- 密钥不落盘到仓库
- 路由规则和模型注册分离
- 每个环境可加载不同配置

---

## 4. 模型路由设计细则

### 4.1 路由输入

路由时建议综合以下信息：

- 用户意图
- 任务复杂度
- 是否需要工具调用
- 是否需要长上下文
- 成本敏感度
- 延迟敏感度
- 用户偏好
- 上下文长度
- 历史执行结果

### 4.2 路由输出

建议输出标准化结构：

```json
{
  "model_id": "gpt-4.1",
  "provider": "openai",
  "reason": "high_reasoning_required",
  "fallback_model": "gpt-4.1-mini"
}
```

### 4.3 路由策略建议

#### 低成本优先
适合高频、简单、低风险任务。

#### 高精度优先
适合复杂推理、代码、长文档总结、任务规划。

#### 长上下文优先
适合阅读大量资料、长对话、多文档比较。

#### 工具调用优先
适合需要调用外部能力的场景。

#### Fallback 优先
当主模型失败时，自动降级到备用模型。

### 4.4 模型路由与 Orchestrator 的关系

- Router 决定是否进入 Orchestrator
- ModelRouter 决定使用哪个模型
- Orchestrator 可在多阶段流程中重复调用 ModelRouter
- 同一套路由策略可跨入口复用

---

## 5. 推荐的调用链

### 5.1 简单任务

```text
User
 ↓
Interface
 ↓
Router
 ↓
ModelRouter
 ↓
LLMClient
 ↓
Response
```

### 5.2 复杂任务

```text
User
 ↓
Interface
 ↓
Router
 ↓
Orchestrator
 ↓
ModelRouter
 ↓
LLMClient
 ↓
Tool Runner
 ↓
Capability
 ↓
Response
```

### 5.3 需要记忆参与的任务

```text
User
 ↓
Interface
 ↓
Router
 ↓
Orchestrator
 ↓
Memory Read
 ↓
ModelRouter
 ↓
LLMClient
 ↓
Capability
 ↓
Memory Write
 ↓
Response
```

---

## 6. 推荐项目结构

```text
project/
├── app/
│   ├── interface/
│   ├── router/
│   │   ├── router.py
│   │   ├── model_router.py
│   │   ├── intent_classifier.py
│   │   └── routing_context.py
│   ├── orchestrator/
│   │   ├── planner.py
│   │   ├── executor.py
│   │   └── workflow.py
│   ├── capability/
│   │   ├── tools/
│   │   ├── wrappers/
│   │   ├── runner.py
│   │   └── state/
│   └── memory/
│       ├── storage/
│       ├── retrieval/
│       └── strategy/
│
├── infra/
│   └── llm/
│       ├── client.py
│       ├── adapter.py
│       └── providers/
│
├── config/
│   ├── model_registry.yaml
│   ├── routing_rules.yaml
│   └── prompts/
│
├── .env
├── main.py
└── pyproject.toml
```

---

## 7. 关键设计边界

### 7.1 Router 不做什么

- 不做工具执行
- 不写 Provider 细节
- 不做复杂工作流编排
- 不管理底层重试与超时
- 不直接耦合具体 SDK

### 7.2 Orchestrator 不做什么

- 不写底层 API 调用
- 不管理 provider 差异
- 不承担配置加载职责
- 不把工具逻辑写成业务逻辑

### 7.3 Capability 不做什么

- 不依赖 Agent 框架
- 不依赖模型
- 不依赖提示词策略
- 不承担编排职责

### 7.4 Infra 不做什么

- 不参与意图判断
- 不参与业务路由
- 不管理领域逻辑
- 不替代配置层

---

## 8. 运行流程说明

### 8.1 用户输入进入系统

1. 用户通过任一入口输入内容
2. Interface Layer 传递给 Router
3. Router 识别意图、判断复杂度
4. Router 通过 ModelRouter 选择模型
5. 若任务简单，则直接调用 LLMClient 并返回结果
6. 若任务复杂，则进入 Orchestrator
7. Orchestrator 组织多步任务
8. 需要工具时调用 Capability
9. 需要记忆时调用 Memory
10. 最终生成响应返回给用户

### 8.2 复杂任务示例

例如用户输入：

> “帮我总结这个文档，然后根据我的历史偏好给出最适合的行动建议。”

流程可能是：

- Router 识别为复杂分析任务
- ModelRouter 选择长上下文强模型
- Orchestrator 读取 Memory
- LLM 做总结
- 必要时调用 Capability 查询外部信息
- 最后组合输出结果

---

## 9. 发展路线

### Phase 1：基础可用
- CLI 优先
- 简单 Router
- Capability 独立化
- 单模型接入

### Phase 2：模型路由与多模型
- 引入 ModelRouter
- 引入 Model Registry
- 支持 fallback
- 支持低成本 / 高性能分流

### Phase 3：编排增强
- 引入 Orchestrator
- 引入多步 workflow
- 支持子任务拆分
- 支持规划模型和执行模型分离

### Phase 4：多入口与多 Agent
- CLI / Desktop / Mobile
- 多 Agent 协同
- 任务调度系统
- 自动化工作流

---

## 10. 一句话总结

> Router 负责决定走哪条路，ModelRouter 负责决定用哪个模型，Config 负责定义有哪些模型，Infra 负责调用模型，Orchestrator 负责完成任务，Capability 负责执行现实世界动作，Memory 负责沉淀长期上下文。

---

## 11. 落地建议

如果你的目标是尽快稳定落地，建议按下面顺序实现：

1. 先完成 Capability Layer 的独立化
2. 再完成 Router Layer 的意图识别与路由
3. 引入 Model Registry 和 ModelRouter
4. 抽出 LLMClient 与 Provider Adapter
5. 最后再引入 Orchestrator 进行多步骤编排

这样可以避免一开始就把系统做复杂，同时保留足够的扩展性。

---
