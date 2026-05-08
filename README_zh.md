# Brix

> **[English](README.md)**

模块化、多供应商 AI Agent，支持状态机编排、工具调用和持久化记忆。

## 特性

- **多供应商 LLM** — 统一接口，同时支持 OpenAI 兼容和 Anthropic 兼容 API
- **双编排引擎** — 纯 Python 状态机 + LangGraph 引擎，配置切换
- **流式输出** — 逐 token 实时渲染，安全边界 Markdown 检测
- **工具调用** — 内置工具：计算器、天气查询（模拟）、文件读取
- **记忆系统 v2** — Session 隔离对话、Agent 人格（soul.md）、用户画像（user.md）、自动 Onboarding
- **持久化存储** — 原子写入 + fcntl 文件锁，崩溃安全
- **智能路由** — 意图分类 + 复杂度评估，自动选择模型
- **Rich 终端 UI** — 动画 Spinner、工具执行面板、启动 Banner、自定义主题、内联响应标记
- **可扩展配置** — 编辑一个 YAML 文件即可添加新供应商和模型
- **流程日志** — 每轮对话自动记录完整数据流，便于调试和审计
- **Hook 系统** — 事件驱动架构，核心模块通过 `hooks.fire()` 触发事件，FlowLog 作为默认监听者

---

## 快速开始

### 1. 克隆 & 环境搭建

```bash
git clone https://github.com/kuicao55/Brix.git
cd Brix

# 创建虚拟环境（需要 Python 3.11+）
python3.11 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e ".[dev]"
```

### 2. 配置 API Key

```bash
# 复制示例文件，填入你的 key
cp .env.example .env
```

编辑 `.env`：

```env
# ZenMux 聚合平台（一个 key 访问所有模型）
ZENMUX_API_KEY=your-zenmux-key-here

# MiniMax 官方 API
MINIMAX_API_KEY=your-minimax-key-here

# Mimo 官方 API
MIMO_API_KEY=your-mimo-key-here
```

> Key 通过 `python-dotenv` 自动加载，无需手动 `export`。

### 3. 运行

```bash
# 方式 A：直接运行
.venv/bin/python main.py

# 方式 B：激活虚拟环境后运行
python main.py
```

---

## Shell 别名（推荐）

配置 shell 别名后，可以在任意目录用一条命令启动 Brix。

### 配置方法

在你的 shell 配置文件中添加一行：

**Zsh**（macOS 默认）— 编辑 `~/.zshrc`：
```bash
alias brix="cd ~/Applications/Brix && .venv/bin/python main.py"
```

**Bash** — 编辑 `~/.bashrc` 或 `~/.bash_profile`：
```bash
alias brix="cd ~/Applications/Brix && .venv/bin/python main.py"
```

> 如果项目路径不同，请替换 `~/Applications/Brix` 为你的实际路径。

然后重新加载 shell 配置：

```bash
source ~/.zshrc   # 或 source ~/.bashrc
```

### 使用

```bash
# 在任意目录启动 Brix
brix

# 就这样 — 不需要激活 venv，也不需要 cd 到项目目录
```

### 删除别名

从 shell 配置文件中删除 `alias brix=...` 那一行，然后重新加载即可。

---

## REPL 命令

| 命令 | 说明 |
|------|------|
| `/quit` | 保存 session 并退出 |
| `/clear` | 开始新 session |
| `/sessions` | 列出最近 session |
| `/resume` | 恢复指定 session |
| `/soul` | 查看 Agent 人格（soul.md） |
| `/user` | 查看用户画像（user.md） |
| `/model` | 显示当前模型 |
| `/log` | 交互式日志查看器（上下箭头选择） |

---

## 流程日志

Brix 会自动记录每轮对话的完整数据流，存储在 `log/data/brix.jsonl`（JSONL 格式）。

### 查看日志

输入 `/log` 打开交互式日志查看器，用上下箭头选择，回车查看详情：

```
you> /log
Select a log entry (arrow keys + Enter):
> #1  2026-05-07T15:36:12 [a3f8b21c]  12500ms OK  "明天上海天气如何？"
  #2  2026-05-07T15:35:05 [49621c65]  7644ms  OK  "你好"
```

选择后显示详细信息：

```
  #1  2026-05-07T15:36:12 [a3f8b21c]  12500ms OK  "明天上海天气如何？"
------------------------------------------------------------
  Trace:  49621c65
  Time:   2026-05-07T15:35:05
  Input:  你好
  Model:  minimax/MiniMax-M2.7
  Status: OK
------------------------------------------------------------
  [1] memory  @15:35:05.203  0.2s
      从存储加载历史记录，裁剪上下文窗口
      msgs: 0, window: 0, chars: 0

  [2] intent  @15:35:09.738  4.5s
      调用 LLM 分类用户意图 (chat/task/tool_use)
      result: chat | via: llm | model: minimax/MiniMax-M2.7
      response: chat

  [3] complexity  @15:35:09.738  0.0s
      基于关键词规则评估请求复杂度
      result: low

  [4] router  @15:35:09.738  0.0s
      根据意图和复杂度选择最佳模型
      model: minimax/MiniMax-M2.7

  [5] orch_plan  @15:35:12.844  3.1s
      调用 LLM 生成回复或决定调用哪些工具
      response: 你好！有什么我可以帮助你的吗？

  [6] persist  @15:35:12.846  0.0s
      将本轮对话保存到存储
      saved: 2
```

### 日志字段说明

每个步骤记录以下信息：

| 字段 | 说明 |
|------|------|
| `@HH:MM:SS.mmm` | 步骤完成的墙钟时间 |
| `X.Xs` | 该步骤的实际耗时 |
| `prompt` | 发送给 LLM 的完整消息列表 |
| `response` | LLM 的原始返回内容 |
| `ms` | LLM 调用或工具执行的精确耗时（毫秒） |

### 记录的步骤

| 步骤 | 说明 |
|------|------|
| `memory` | 从存储加载历史，构建上下文窗口 |
| `intent` | LLM 分类用户意图，记录 prompt 和响应 |
| `complexity` | 基于规则评估请求复杂度 |
| `router` | 根据意图和复杂度选择模型 |
| `orch_plan` | LLM 生成回复或决定工具调用，记录完整 prompt |
| `tool_exec` | 执行工具并记录输入/输出 |
| `persist` | 将对话保存到存储 |

---

## 配置指南

所有配置都在 `config/settings.yaml` 中。编辑这一个文件即可添加供应商、模型和修改行为。

### 添加新供应商

供应商就是一个 API 端点。在 `providers:` 下添加 3 行：

```yaml
providers:
  # 已有供应商...

  deepseek:                              # 供应商名称（任意唯一 key）
    base_url: "https://api.deepseek.com/anthropic"  # API 端点
    api_key_env: "DEEPSEEK_API_KEY"     # API key 对应的环境变量名
    protocol: "anthropic"               # "anthropic" 或 "openai"
```

然后在 `.env` 中添加 API key：

```env
DEEPSEEK_API_KEY=your-key-here
```

**协议选择：**
- `"anthropic"` — 使用 Anthropic Messages 格式的 API（如 Claude、MiniMax、Mimo）
- `"openai"` — 使用 OpenAI Chat Completions 格式的 API（如 GPT、通过 ZenMux 的 DeepSeek）

### 添加新模型

在 `models:` 下添加一条：

```yaml
models:
  # 已有模型...

  - id: "deepseek/deepseek-chat"         # 格式：供应商/模型名
    provider: "deepseek"                  # 必须匹配 providers 中的 key
    purpose: ["fast_chat", "coding"]      # 何时使用此模型
    capabilities: ["tool_calling"]        # 支持的功能
    max_context: 64000                    # 上下文窗口大小
    cost_tier: "low"                      # "low"、"medium" 或 "high"
```

### 模型 ID 格式

模型 ID 遵循 `供应商/模型名` 的格式：

| 示例 ID | 供应商 | 模型 |
|---------|--------|------|
| `minimax/MiniMax-M2.7` | minimax | MiniMax-M2.7 |
| `mimo/mimo-v2.5-pro` | mimo | mimo-v2.5-pro |
| `zenmux-openai/deepseek/deepseek-v4-pro` | zenmux-openai | deepseek/deepseek-v4-pro |

对于 ZenMux 这类聚合平台，模型名包含供应商前缀（如 `deepseek/deepseek-v4-pro`）。

### 模型字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 模型唯一标识（`供应商/模型名`） |
| `provider` | string | 必须匹配 `providers` 中的某个 key |
| `purpose` | list | 使用场景：`fast_chat`、`coding`、`reasoning`、`planning`、`analysis`、`simple_qa`、`image_generation`、`video_generation` |
| `capabilities` | list | 功能特性：`tool_calling`、`strong_reasoning`、`low_latency`、`low_cost`、`long_context`、`image_generation`、`video_generation` |
| `max_context` | int | 上下文窗口（token 数） |
| `cost_tier` | string | `"low"`、`"medium"` 或 `"high"` |
| `default` | bool | 设为 `true` 则为默认模型（可选） |

### 默认模型 & 备用模型

```yaml
routing:
  default_model: "minimax/MiniMax-M2.7"                    # 主力模型
  fallback_model: "zenmux-openai/deepseek/deepseek-v4-flash"  # 主力模型失败时使用
```

---

## 切换编排引擎

Brix 有两个编排引擎，控制 Agent 如何处理请求：

| 引擎 | 说明 | 适用场景 |
|------|------|----------|
| `state_machine` | 纯 Python 状态机，无额外依赖 | 默认推荐，轻量快速 |
| `langgraph` | LangGraph StateGraph 图编排，需要安装 `langgraph` | 复杂多步任务，调试可视化 |

### 如何切换

编辑 `config/settings.yaml`，修改 `engine` 字段：

```yaml
engine: "state_machine"   # 纯 Python（默认）
```

或：

```yaml
engine: "langgraph"       # LangGraph StateGraph
```

保存文件，下次启动即生效。

### 安装 LangGraph

如果想使用 `langgraph` 引擎，需要安装：

```bash
pip install langgraph
```

如果未安装 LangGraph 但设置了 `engine: "langgraph"`，Brix 会自动回退到 `state_machine` 并显示警告。

### 如何选择？

- **`state_machine`** — 推荐大多数用户使用。简单、快速、无额外依赖。
- **`langgraph`** — 需要基于图的编排和显式状态转换时使用。更适合调试复杂的多工具工作流。

---

## 架构

```
+-----------------------------------------------------+
|                      CLI 层                          |
|                  cli/app.py (REPL)                   |
+-----------------------------------------------------+
|                    路由层                             |
|  router/intent.py  router/complexity.py              |
|  router/model_router.py                              |
+-----------------------------------------------------+
|                   编排层                              |
|  orchestrator/state_machine.py  (纯 Python)          |
|  orchestrator/langgraph_engine.py (LangGraph)        |
+-----------------------------------------------------+
|                   能力层                              |
|  capability/runner.py (ToolRunner)                   |
|  capability/tools/calculator.py                      |
|  capability/tools/weather.py                         |
|  capability/tools/file_read.py                       |
+-----------------------------------------------------+
|                   基础设施层                          |
|  infra/llm_client.py (统一 LLM 客户端)               |
|  infra/providers/openai_compat.py                    |
|  infra/providers/anthropic_compat.py                 |
+-----------------------------------------------------+
|                    配置层                             |
|  config/loader.py  config/model_registry.py          |
|  config/settings.yaml                                |
+-----------------------------------------------------+
|                    记忆层                             |
|  memory/__init__.py (MemoryProvider Protocol)         |
|  memory/provider.py (BrixMemoryProvider 实现)         |
|  memory/session.py (Session 管理 + 文件锁)            |
|  memory/soul.py (Agent 人格)                          |
|  memory/user.py (用户画像)                            |
|  memory/storage.py (原子 JSON 存储)                   |
|  memory/strategy.py (上下文窗口管理)                   |
+-----------------------------------------------------+
|                    日志层                             |
|  log/flow.py (流程日志收集器)                         |
|  log/writer.py (JSONL 文件读写)                       |
+-----------------------------------------------------+
|                   Hook 层                             |
|  hooks/registry.py (HookRegistry + HookEvent)        |
|  核心模块触发事件 → FlowLog 自动接收                  |
+-----------------------------------------------------+
|                  终端 UI 层                           |
|  cli/stream_renderer.py (Markdown 流式渲染)           |
|  cli/spinner.py (Braille 点动画)                      |
|  cli/stage_indicator.py (统一加载 Spinner)             |
|  cli/tool_display.py (工具执行面板)                    |
|  cli/theme.py (Rich 主题)                             |
|  cli/banner.py (启动 Banner)                          |
+-----------------------------------------------------+
```

### 数据流

```
用户输入
    |
    v
意图分类 (chat / task / tool_use)
    |
    v
复杂度评估 (low / medium / high)
    |
    v
模型选择 (基于意图 + 复杂度 + 配置)
    |
    v
编排循环
    |
    +---> LLM 调用 ---> 有工具调用? ---> 执行工具 ---> 审查 --+
    |                                                         |
    +---------------------------------------------------------+
    |
    v
响应 + 记忆持久化
```

---

## 项目结构

```
brix/
+-- main.py                          # 入口
+-- pyproject.toml                   # 项目配置 & 依赖
+-- config/
|   +-- settings.yaml                # 供应商 & 模型配置
|   +-- loader.py                    # YAML 配置加载器
|   +-- model_registry.py           # 模型查找（按 id/purpose）
+-- infra/
|   +-- llm_client.py               # 统一 LLM 客户端
|   +-- providers/
|       +-- openai_compat.py        # OpenAI 兼容适配器
|       +-- anthropic_compat.py     # Anthropic 兼容适配器
+-- router/
|   +-- intent.py                   # 意图分类
|   +-- complexity.py               # 复杂度评估
|   +-- model_router.py             # 模型选择逻辑
+-- orchestrator/
|   +-- engine.py                   # OrchestratorEngine 协议
|   +-- states.py                   # 状态枚举
|   +-- state_machine.py            # 纯 Python 状态机
|   +-- langgraph_engine.py         # LangGraph 引擎
+-- capability/
|   +-- base.py                     # Tool 抽象基类
|   +-- runner.py                   # ToolRunner 注册表
|   +-- tools/
|       +-- calculator.py           # 数学表达式计算器
|       +-- weather.py              # 天气查询（模拟）
|       +-- file_read.py            # 本地文件读取
|       +-- file_write.py           # 文件写入（memory/data/ 沙箱）
|       +-- file_edit.py            # 文件编辑（memory/data/ 沙箱）
+-- memory/
|   +-- __init__.py                 # MemoryProvider Protocol + 工厂函数
|   +-- provider.py                 # BrixMemoryProvider 实现
|   +-- session.py                  # Session 管理（UUID、文件锁）
|   +-- soul.py                     # Agent 人格（soul.md）
|   +-- user.py                     # 用户画像（user.md）
|   +-- storage.py                  # 原子 JSON 持久化
|   +-- strategy.py                 # 上下文窗口管理
|   +-- data/                       # 运行时数据（gitignore）
+-- log/
|   +-- flow.py                     # FlowLog 流程日志收集器
|   +-- writer.py                   # JSONL 文件读写
+-- hooks/
|   +-- registry.py                 # HookRegistry + HookEvent
|   +-- __init__.py                 # Re-exports
+-- cli/
|   +-- app.py                      # REPL 界面（流式管线）
|   +-- display.py                  # 输出格式化
|   +-- stream_renderer.py          # 安全边界 Markdown 流式渲染器
|   +-- spinner.py                  # Braille 点动画 Spinner
|   +-- stage_indicator.py          # 统一加载 Spinner (原地更新)
|   +-- tool_display.py             # 工具执行状态面板
|   +-- theme.py                    # Rich 主题 (markdown, tool, spinner 样式)
|   +-- banner.py                   # 启动 ASCII Banner
+-- tests/
    +-- test_config.py              # 配置层测试
    +-- test_infra.py               # 基础设施层测试
    +-- test_orchestrator.py        # 编排层测试
    +-- test_langgraph.py           # LangGraph 引擎测试
    +-- test_router.py              # 路由层测试
    +-- test_capability.py          # 工具 & runner 测试
    +-- test_memory.py              # 记忆层测试
    +-- test_cli.py                 # CLI 测试
    +-- test_flow_log.py            # 流程日志测试
```

---

## 测试

```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行所有测试
python -m pytest tests/ -v

# 运行特定模块
python -m pytest tests/test_orchestrator.py -v

# 运行并查看覆盖率
python -m pytest tests/ --cov=. --cov-report=term-missing
```

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 异步 | asyncio |
| REPL | prompt_toolkit |
| 终端 UI | Rich (Live, Markdown, Panel, Theme) |
| 配置 | PyYAML |
| HTTP | httpx |
| LLM (OpenAI) | openai SDK |
| LLM (Anthropic) | anthropic SDK |
| 编排 | langgraph（可选） |
| 环境变量 | python-dotenv |
| 测试 | pytest + pytest-asyncio |

---

## 许可证

私有项目。
