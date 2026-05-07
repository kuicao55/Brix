# Brix 改进方案报告

> 基于对 Claude Code (官方 TypeScript 实现) 和 Claw Code (Rust 重实现) 的深入分析，
> 结合 Brix "速度快、可扩展、部署方便" 的定位，整理出以下改进方案。

---

## 一、三个项目对比总览

| 维度 | Brix (当前) | Claude Code (官方) | Claw Code (Rust 重实现) |
|------|-------------|-------------------|------------------------|
| 语言 | Python 3.11+ | TypeScript + React/Ink | Rust (6 crates) |
| Agent 循环 | 状态机/LangGraph 双引擎 | AsyncGenerator 状态机 | 泛型 `ConversationRuntime<C,T>` |
| 工具系统 | ABC 继承 + ToolRunner 注册 | 丰富接口 (权限/渲染/分类/并发) | Trait 抽象 + 静态注册表 |
| 流式输出 | 无 | 全链路 SSE 流式 | SSE 流式 + 终端 spinner |
| 上下文管理 | 字符数截断 (4000 字) | 多层压缩 (auto/micro/snip/collapse) | Token 阈值自动压缩 |
| 扩展机制 | 子类化 Tool | Hooks + Plugins + Skills + MCP | Hooks + MCP + 自定义命令 |
| 配置 | 单 YAML 文件 | 多层级合并 (全局/项目/本地/CLI/env) | 三层 JSON 合并 |
| 权限系统 | 文件读取有路径检查 | 完整分级权限 + 规则匹配 | 分级权限 + 交互式确认 |
| 部署 | pip install | npm 全局安装 | cargo build 单二进制 |

**核心判断**：Brix 的 7 层架构骨架设计良好，但缺少"血肉"——流式体验、上下文智能管理、扩展钩子这三个日常助手最关键的能力。下面按优先级分层给出改进方案。

---

## 二、P0 — 必须优先改进（影响日常使用体验）

### 2.1 流式输出 (Streaming Output)

**现状问题**：Brix 当前等待 LLM 完整返回后才显示，用户看到的是"空白等待 → 一大段文字"，体感慢。

**参考实现**：
- Claude Code：全链路 AsyncGenerator，从 API SSE 事件 → 文本增量 → 终端实时渲染，工具调用也是流式解析
- Claw Code：Rust 端 `AssistantEvent` 枚举 (`TextDelta`, `ToolUse`, `Usage`, `MessageStop`)，边收边渲染

**改进方案**：

```python
# infra/providers/openai_compat.py — 改用 stream=True
async def chat_stream(self, messages, tools=None, model=None):
    """yield 文本增量和工具调用块"""
    response = await self.client.chat.completions.create(
        model=model, messages=messages, tools=tools, stream=True
    )
    async for chunk in response:
        delta = chunk.choices[0].delta
        if delta.content:
            yield {"type": "text_delta", "text": delta.content}
        if delta.tool_calls:
            yield {"type": "tool_use", "data": delta.tool_calls}
```

```python
# orchestrator/engine.py — 新增流式协议方法
class OrchestratorEngine(Protocol):
    async def run_stream(self, ctx: OrchestratorContext) -> AsyncGenerator[str, None]:
        """流式输出文本增量，工具调用时暂停输出工具名"""
        ...
```

```python
# cli/app.py — REPL 改为流式消费
async for chunk in engine.run_stream(ctx):
    print(chunk, end="", flush=True)
```

**工作量**：中等 (2-3 天)。需要改 LLM Client、Orchestrator、CLI 三层。
**收益**：体感速度提升 3-5 倍，这是日常助手最核心的体验差距。

### 2.2 上下文智能管理 (Context Compaction)

**现状问题**：`MemoryStrategy` 用字符数截断到 4000 字符，这会导致：
- 多轮对话时丢失早期重要上下文
- 不区分消息重要性，可能丢掉系统指令
- 字符数 ≠ Token 数，截断不精确

**参考实现**：
- Claude Code：5 层压缩策略 (auto-compact / reactive / micro-compact / snip / context-collapse)
- Claw Code：累计 input tokens 超过阈值 (默认 200K) 时自动压缩，保留最近消息 + 关键文件 + 待办事项

**改进方案**（分三步）：

**Step 1 — Token 计数替代字符计数** (1 天)
```python
# memory/strategy.py
import tiktoken

class MemoryStrategy:
    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens
        self.encoder = tiktoken.encoding_for_model("gpt-4")  # 通用近似

    def get_context_window(self, history: list[dict]) -> list[dict]:
        """按 token 数截断，保留最近对话"""
        total = 0
        result = []
        for msg in reversed(history):
            tokens = len(self.encoder.encode(json.dumps(msg, ensure_ascii=False)))
            if total + tokens > self.max_tokens:
                break
            result.append(msg)
            total += tokens
        return list(reversed(result))
```

**Step 2 — 智能压缩** (2-3 天)
```python
# memory/compaction.py — 新增
class AutoCompactor:
    """当 token 超过阈值，用 LLM 总结早期对话"""

    def __init__(self, llm_client, threshold_tokens: int = 8000):
        self.llm = llm_client
        self.threshold = threshold_tokens

    async def maybe_compact(self, history: list[dict]) -> list[dict]:
        total = self._count_tokens(history)
        if total < self.threshold:
            return history

        # 保留最近 1/3 的消息不动
        split = len(history) * 2 // 3
        old_messages = history[:split]
        recent_messages = history[split:]

        # 用 LLM 总结早期对话
        summary = await self._summarize(old_messages)

        # 替换为摘要 + 原始上下文标记
        return [
            {"role": "system", "content": f"[对话摘要]\n{summary}"},
            *recent_messages,
        ]
```

**Step 3 — 结构化摘要** (可选，后期)
保留关键文件路径、待办事项、用户偏好等结构化信息，而非纯文本摘要。

**收益**：支持长对话不丢失上下文，日常助手的核心需求。

### 2.3 LLM 调用重试与错误处理

**现状问题**：LLM 调用失败直接抛异常或走 heuristic fallback，没有重试机制。日常使用中网络波动、API 限流很常见。

**参考实现**：
- Claw Code：指数退避重试 + OAuth token 刷新
- Claude Code：API 层有 retry logic + fallback model

**改进方案** (1 天)：
```python
# infra/llm_client.py
import asyncio
from functools import wraps

async def retry_with_backoff(coro_func, max_retries=3, base_delay=1.0):
    for attempt in range(max_retries):
        try:
            return await coro_func()
        except (RateLimitError, TimeoutError, ConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)

# 在 LLMClient.chat() 中使用
async def chat(self, messages, tools=None, model=None):
    provider = self._get_provider(model)
    return await retry_with_backoff(
        lambda: provider.chat(messages, tools, model)
    )
```

**收益**：减少日常使用中的失败率，提升稳定性。

---

## 三、P1 — 重要改进（提升扩展性）

### 3.1 Hook/Event 系统 ✅ 已完成

> **实现位置**: `hooks/registry.py` — `HookRegistry` + `HookEvent`，独立顶层模块
> **集成状态**: `cli/app.py` 初始化 HookRegistry 并绑定 FlowLog，所有核心模块通过 `hooks.fire()` 触发事件

**现状问题**：工具执行是硬编码流程，无法在不修改核心代码的情况下注入行为（如日志增强、权限检查、输入修正）。

**参考实现**：
- Claude Code：完整的 Hook 系统，支持 `PreToolUse` / `PostToolUse` / `UserPromptSubmit` / `SessionStart` 等 20+ 事件类型，Hook 类型包括 shell 命令、LLM prompt、agent 验证器、HTTP webhook
- Claw Code：`HookRunner` 通过 exit code 控制允许/拒绝 (0=allow, 2=deny)

**改进方案**（轻量版，适合 Brix 定位）：

```python
# infra/hooks.py — 新增
from dataclasses import dataclass
from typing import Callable, Any

@dataclass
class HookEvent:
    name: str           # "pre_tool_use" / "post_tool_use" / "pre_llm_call"
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_output: str | None = None
    context: dict | None = None

class HookResult:
    allow: bool = True
    modified_input: dict | None = None   # 可以修改工具输入
    message: str | None = None           # 附加消息

class HookRegistry:
    def __init__(self):
        self._hooks: dict[str, list[Callable]] = {}

    def register(self, event: str, hook: Callable[[HookEvent], HookResult]):
        self._hooks.setdefault(event, []).append(hook)

    async def run(self, event: HookEvent) -> HookResult:
        result = HookResult()
        for hook in self._hooks.get(event.name, []):
            hr = hook(event)
            if not hr.allow:
                return hr  # 立即拒绝
            if hr.modified_input:
                result.modified_input = hr.modified_input
        return result
```

在 `ToolRunner.run()` 中插入 Hook 调用：
```python
async def run(self, tool_name, params, hook_registry=None):
    if hook_registry:
        event = HookEvent(name="pre_tool_use", tool_name=tool_name, tool_input=params)
        hr = await hook_registry.run(event)
        if not hr.allow:
            return f"工具被拒绝: {hr.message}"
        if hr.modified_input:
            params = hr.modified_input

    result = await self._tools[tool_name].execute(**params)

    if hook_registry:
        event = HookEvent(name="post_tool_use", tool_name=tool_name, tool_output=result)
        await hook_registry.run(event)

    return result
```

**工作量**：1-2 天。
**收益**：这是 Brix 扩展性的基石——有了 Hook，用户可以在不修改 Brix 代码的情况下：
- 添加权限检查（哪些工具需要确认）
- 添加日志/审计
- 修改工具输入（如自动添加路径前缀）
- 集成外部系统（如 Slack 通知）

### 3.2 Skill / 快捷命令系统

**现状问题**：Brix 只有 REPL 输入框，没有预设的快捷操作。

**参考实现**：
- Claude Code：Skills 系统，`/commit`、`/review-pr`、`/simplify` 等，可从 `.claude/skills/` 目录加载自定义 Skill
- Claw Code：自定义 `/bughunter`、`/ultraplan`、`/teleport` 等

**改进方案** (2 天)：

```python
# capability/skill.py — 新增
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Skill:
    name: str           # "commit"
    description: str    # "提交代码并生成 commit message"
    prompt: str         # 预设的 system prompt 或指令模板
    tools_required: list[str] | None = None  # 需要哪些工具

class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill):
        self._skills[skill.name] = skill

    def load_from_dir(self, path: Path):
        """从 .claude/skills/ 或 skills/ 目录加载 markdown 文件"""
        for f in path.glob("*.md"):
            name = f.stem
            content = f.read_text()
            # 解析 frontmatter 和 body
            self.register(Skill(name=name, description="", prompt=content))

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())
```

内置几个日常助手常用的 Skill：
- `/commit` — 分析 diff，生成 commit message
- `/summarize` — 总结当前对话
- `/remind` — 设置提醒（结合 cron）
- `/explain` — 解释代码或概念

**收益**：提升日常使用效率，Skill 文件是纯 Markdown，用户可以轻松自定义。

### 3.3 层级化配置系统

**现状问题**：单个 `settings.yaml` 无法区分全局默认、项目配置、本地覆盖。

**参考实现**：
- Claude Code：7 层配置合并 (remote → MDM → global → project → local → CLI → env)
- Claw Code：3 层 JSON 合并 (user → project → local)

**改进方案** (1 天)：

```python
# config/loader.py — 改进
from pathlib import Path
import yaml

class ConfigLoader:
    """层级化配置加载：global → project → local → env"""

    LAYERS = [
        Path.home() / ".brix" / "config.yaml",           # 全局
        Path.cwd() / ".brix" / "settings.yaml",           # 项目
        Path.cwd() / ".brix" / "settings.local.yaml",     # 本地 (gitignore)
    ]

    def load(self) -> dict:
        merged = {}
        for layer in self.LAYERS:
            if layer.exists():
                with open(layer) as f:
                    self._deep_merge(merged, yaml.safe_load(f) or {})
        # 环境变量覆盖
        self._apply_env_overrides(merged)
        return merged

    def _deep_merge(self, base: dict, override: dict):
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v
```

**收益**：项目级配置可以提交到 git 共享，本地密钥/偏好可以 gitignore，全局配置跨项目复用。

---

## 四、P2 — 锦上添花（提升健壮性和未来扩展）

### 4.1 MCP (Model Context Protocol) 支持

**现状问题**：工具只能通过 Python 代码添加，无法动态接入外部工具服务。

**参考实现**：
- Claude Code：完整 MCP 客户端，支持 stdio / SSE / HTTP / WebSocket 传输
- Claw Code：6 种 MCP 传输类型

**改进方案**：先支持 stdio 传输（最简单），通过 JSON-RPC 与 MCP server 通信。

```python
# infra/mcp_client.py — 新增 (后期)
class MCPClient:
    """通过 stdio 与 MCP server 通信，自动注册其工具"""

    async def connect(self, command: str, args: list[str]):
        self.proc = await asyncio.create_subprocess_exec(
            command, *args,
            stdin=PIPE, stdout=PIPE, stderr=PIPE
        )
        tools = await self._list_tools()
        return tools  # 返回 Tool 列表，可注册到 ToolRunner
```

**工作量**：3-5 天。
**收益**：接入丰富的 MCP 生态（数据库、浏览器、文件系统、API 等），大幅扩展 Brix 能力而无需自己写工具。

### 4.2 工具并发执行

**现状问题**：工具串行执行，当 LLM 一次返回多个工具调用时会依次等待。

**参考实现**：
- Claude Code：`isConcurrencySafe()` 标记 + 并行批次执行，最多 10 个并发
- 工具分为"安全可并发"（读取类）和"不安全"（写入类）

**改进方案** (1 天)：

```python
# capability/runner.py — 改进
import asyncio

class ToolRunner:
    async def run_batch(self, tool_calls: list[dict]) -> list[str]:
        """并发执行安全的工具，串行执行不安全的工具"""
        results = []
        safe_batch = []
        unsafe_batch = []

        for call in tool_calls:
            tool = self._tools[call["name"]]
            if getattr(tool, "is_read_only", False):
                safe_batch.append(call)
            else:
                unsafe_batch.append(call)

        # 并发执行安全工具
        if safe_batch:
            safe_results = await asyncio.gather(
                *[self.run(c["name"], c["params"]) for c in safe_batch]
            )
            results.extend(safe_results)

        # 串行执行不安全工具
        for call in unsafe_batch:
            results.append(await self.run(call["name"], call["params"]))

        return results
```

**收益**：多工具调用场景下速度提升明显（如同时读取多个文件）。

### 4.3 System Prompt 动态组装

**现状问题**：System prompt 是静态的，无法根据工具、上下文动态调整。

**参考实现**：
- Claude Code：`SystemPromptBuilder` 动态组装多段 prompt (工具描述、环境信息、项目上下文、git status 等)
- 每个工具的 `prompt()` 方法贡献自己的说明段落

**改进方案**：

```python
# orchestrator/prompt_builder.py — 新增
class SystemPromptBuilder:
    def __init__(self):
        self._sections: list[str] = []

    def add(self, section: str):
        self._sections.append(section)

    def add_tool_prompts(self, tools: list[Tool]):
        for tool in tools:
            if hasattr(tool, 'prompt'):
                self._sections.append(tool.prompt())

    def add_context(self, cwd: str, date: str, platform: str):
        self._sections.append(
            f"环境: {platform} | 工作目录: {cwd} | 日期: {date}"
        )

    def build(self) -> str:
        return "\n\n".join(self._sections)
```

**收益**：让 LLM 更了解当前环境和可用工具，提升响应质量。

### 4.4 权限系统

**现状问题**：只有 `FileReadTool` 有路径检查，其他工具无权限控制。

**改进方案**（轻量版）：

```python
# infra/permissions.py — 新增
from enum import IntEnum

class PermissionLevel(IntEnum):
    READ_ONLY = 0
    WORKSPACE_WRITE = 1
    FULL_ACCESS = 2

class PermissionPolicy:
    def __init__(self, mode: PermissionLevel = PermissionLevel.FULL_ACCESS):
        self.mode = mode

    def check(self, tool: Tool) -> bool:
        required = getattr(tool, 'required_permission', PermissionLevel.READ_ONLY)
        return self.mode >= required
```

在 `Tool` 基类中添加 `required_permission` 属性，默认为 `READ_ONLY`。写操作类工具设为 `WORKSPACE_WRITE`。

**收益**：为未来接入敏感操作（如删除文件、发送消息）提供安全保障。

---

## 五、架构层面的改进建议

### 5.1 用 AsyncGenerator 重写 Orchestrator

**当前**：`run()` 方法返回 `str`，阻塞式。
**改进**：改为 `AsyncGenerator[str, None]`，支持流式输出。

这是 P1 流式输出的基础，也是 Claude Code 和 Claw Code 的核心设计模式。

```python
# orchestrator/engine.py
class OrchestratorEngine(Protocol):
    async def run(self, ctx: OrchestratorContext) -> AsyncGenerator[str, None]:
        """每次 yield 一个文本增量或工具状态更新"""
        ...
        yield "正在思考..."
        ...
        yield "调用工具: calculator"
        ...
        yield "结果是 42"
```

### 5.2 解决 `OrchestratorContext` 中的 `Any` 类型

**当前**：为避免循环导入，`tool_runner`、`llm_client`、`log` 都是 `Any`。
**改进**：使用 `TYPE_CHECKING` 守卫 + 前向引用。

```python
# orchestrator/engine.py
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from capability.runner import ToolRunner
    from infra.llm_client import LLMClient
    from log.flow import FlowLog

@dataclass
class OrchestratorContext:
    model_id: str
    messages: list[dict]
    tool_runner: ToolRunner        # 不再是 Any
    llm_client: LLMClient          # 不再是 Any
    log: FlowLog                   # 不再是 Any
```

**收益**：类型安全，IDE 补全更好，减少运行时错误。

### 5.3 工具自动发现

**当前**：新工具需要在 `cli/app.py::_register_tools()` 中手动注册。
**改进**：扫描 `capability/tools/` 目录，自动发现并注册。

```python
# capability/registry.py — 新增
import importlib
import inspect
from pathlib import Path

def discover_tools(tools_dir: Path) -> list[Tool]:
    """扫描目录，自动发现 Tool 子类"""
    tools = []
    for py_file in tools_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        module = importlib.import_module(f"capability.tools.{py_file.stem}")
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Tool) and obj is not Tool:
                tools.append(obj())
    return tools
```

**收益**：添加新工具只需在 `capability/tools/` 下新建文件，无需修改其他代码。真正实现"模块分离"。

---

## 六、不建议采纳的特性

以下特性虽然 Claude Code / Claw Code 有，但不适合 Brix 的"日常助手、速度快、部署方便"定位：

| 特性 | 原因 |
|------|------|
| 完整的 Plugin 系统 | 过度工程化，Brix 的工具系统 + Hook 已足够 |
| 子 Agent / Fork 机制 | 日常助手不需要多 Agent 协作，增加复杂度 |
| Git Worktree 隔离 | 这是编码助手的需求，非日常助手 |
| 终端 UI 框架 (React/Ink) | Python 生态用 Rich 就够，不需要引入重框架 |
| MCP Server 模式 | Brix 是客户端，不需要暴露为 MCP Server |
| 企业级权限 (MDM/策略) | 个人助手不需要 |
| 多语言 (Rust) 重写 | Python 开发效率高，Brix 不追求极致性能 |

---

## 七、推荐实施路线图

```
Phase 1 — 体验提升 (1-2 周)
├── [P0] 流式输出 — 改 LLM Client + Orchestrator + CLI
├── [P0] Token 计数 — 替换 MemoryStrategy
├── [P0] LLM 重试 — 添加指数退避
└── [P1] 层级化配置 — 改 ConfigLoader

Phase 2 — 扩展性基础 (1-2 周)
├── [P1] Hook 系统 — 新增 infra/hooks.py
├── [P1] Skill 系统 — 新增 capability/skill.py
├── [P2] 工具自动发现 — 改 capability/runner.py
└── [P2] System Prompt 动态组装

Phase 3 — 健壮性 (1 周)
├── [P2] 上下文智能压缩 — AutoCompactor
├── [P2] 工具并发执行
├── [P2] 权限系统
└── [P2] 类型安全改进

Phase 4 — 生态接入 (2 周+)
├── [P2] MCP 客户端 (stdio)
├── 更多内置工具 (日历、邮件、笔记等)
└── Web 入口 (FastAPI + WebSocket)
```

---

## 八、关键文件改动清单

| 文件 | 改动内容 | 优先级 |
|------|----------|--------|
| `infra/llm_client.py` | 添加 stream 方法 + retry 逻辑 | P0 |
| `infra/providers/openai_compat.py` | 实现 SSE 流式 | P0 |
| `infra/providers/anthropic_compat.py` | 实现 Anthropic 流式 | P0 |
| `orchestrator/engine.py` | 协议增加 `run_stream` | P0 |
| `orchestrator/state_machine.py` | 实现流式执行 | P0 |
| `memory/strategy.py` | Token 计数替代字符计数 | P0 |
| `memory/compaction.py` | 新增：自动压缩 | P1 |
| `config/loader.py` | 层级化配置加载 | P1 |
| `infra/hooks.py` | 新增：Hook 注册与执行 | P1 |
| `capability/skill.py` | 新增：Skill 注册与加载 | P1 |
| `capability/runner.py` | 工具自动发现 + 并发执行 | P2 |
| `cli/app.py` | 适配流式输出 + Skill 命令 | P0/P1 |
| `cli/display.py` | 流式渲染 + 可选 Rich 美化 | P0 |

---

## 九、总结

Brix 的 7 层架构骨架是好的——Protocol/ABC 的抽象、YAML 配置驱动、FlowLog 可观测性都体现了良好的设计品味。核心差距在于：

1. **没有流式输出** — 这是日常助手最大的体验短板
2. **上下文管理太简单** — 字符截断无法支撑长对话
3. **缺少 Hook 机制** — 扩展需要改核心代码

这三个问题解决后，Brix 就具备了一个实用日常助手的基础能力。后续的 Skill 系统、MCP 支持、工具自动发现则是让 Brix 从"能用"变成"好用"的关键。

**总原则**：借鉴 Claude Code / Claw Code 的设计思想，但保持 Brix 的轻量定位。不追求功能全面，追求每个功能都简单好用。

---

## 十、详细设计：FlowLog 重构到 Hook 系统 ✅ 已完成

> **实际实现**: `hooks/` 顶层目录（非 `infra/hooks.py`），其余设计与本文一致
> **已完成内容**: HookRegistry + HookEvent (hooks/registry.py)、cli/app.py 绑定、router/intent.py 和 orchestrator/ 全部迁移为 hooks.fire()、测试适配

### 10.1 背景与动机

当前 FlowLog 的 `log.step()` 调用分散在 4 个模块中，每个模块需要显式接收 `log` 参数：

```
cli/app.py           → log.step("memory", ...), log.step("complexity", ...), log.step("router", ...), log.step("persist", ...)
router/intent.py     → log.step("intent", ...)
orchestrator/state_machine.py  → log.step("orch_plan", ...), log.step("tool_exec", ...)
orchestrator/langgraph_engine.py → log.step("orch_plan", ...), log.step("tool_exec", ...)
```

**问题**：核心模块（router、orchestrator）与 log 系统强耦合。新增模块时必须加 `log` 参数、调用 `log.step()`，改动链路长。

**目标**：将 FlowLog 构建在 Hook 系统之上，核心模块只触发事件，不关心谁在监听。

### 10.2 设计方案

#### 核心思路

```
之前:  核心模块 ---(显式调用)---> FlowLog.step()
之后:  核心模块 ---(fire event)---> HookRegistry ---(自动转发)---> FlowLog.step()
                                      |
                                      +---> 其他自定义 hook (权限检查、通知等)
```

#### HookRegistry 设计

```python
# infra/hooks.py — 新增文件 (~50 行)
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class HookEvent:
    """Hook 事件载体"""
    name: str                          # 事件名，如 "intent", "orch_plan"
    data: dict[str, Any] = field(default_factory=dict)  # 事件数据

class HookRegistry:
    """轻量级事件注册与分发中心"""

    def __init__(self) -> None:
        self._hooks: dict[str, list[Callable[[HookEvent], None]]] = {}
        self._log: Any = None  # FlowLog，可选绑定

    def bind_log(self, log: Any) -> None:
        """绑定 FlowLog 实例，所有事件自动转发到 log.step()"""
        self._log = log

    def register(self, event: str, hook: Callable[[HookEvent], None]) -> None:
        """注册自定义 hook，可监听任意事件"""
        self._hooks.setdefault(event, []).append(hook)

    def fire(self, event: str, **data: Any) -> None:
        """
        触发事件（同步）。
        1. 转发到 FlowLog.step()（如果已绑定）
        2. 调用所有注册的自定义 hook
        """
        # 转发到 FlowLog
        if self._log is not None:
            self._log.step(event, **data)

        # 调用自定义 hook
        hook_event = HookEvent(name=event, data=data)
        for hook in self._hooks.get(event, []):
            hook(hook_event)
```

**关键设计决策**：
- `fire()` 是**同步**方法，不需要 `await`。当前 FlowLog.step() 就是同步的，保持一致可以最小化改动。
- `bind_log()` 让 FlowLog 成为 Hook 的一个监听者，而非唯一消费者。未来可以 `register()` 更多 hook。
- 性能开销：无 hook 时 = 1 次 `dict.get()` + 1 次空列表遍历 ≈ 100ns，相比 LLM 调用 (500ms+) 可忽略。

#### FlowLog 本身不变

`log/flow.py` 和 `log/writer.py` **完全不需要改动**。FlowLog 从 HookRegistry 的 `bind_log()` 接收事件，和之前直接被调用的 `.step()` 效果完全一样。

### 10.3 各模块改动详解

#### 10.3.1 `cli/app.py` — 初始化与绑定

```python
# 改动前
from log.flow import FlowLog

async def _process(self, user_input: str) -> str:
    log = FlowLog(user_input)
    ...
    intent = await classify_intent(user_input, context_window, self._llm_client, default_model, log=log)
    ...
    context = OrchestratorContext(history=..., tool_runner=..., log=log)

# 改动后
from log.flow import FlowLog
from infra.hooks import HookRegistry

async def _process(self, user_input: str) -> str:
    log = FlowLog(user_input)
    hooks = HookRegistry()
    hooks.bind_log(log)           # FlowLog 成为 hook 的监听者

    # 可选：注册自定义 hook
    # hooks.register("tool_exec", lambda e: print(f"[debug] tool: {e.data.get('name')}"))

    ...
    intent = await classify_intent(user_input, context_window, self._llm_client, default_model, hooks=hooks)
    ...
    context = OrchestratorContext(history=..., tool_runner=..., hooks=hooks)  # hooks 替代 log
```

#### 10.3.2 `router/intent.py` — 去掉 log 参数

```python
# 改动前
async def classify_intent(user_input, history, llm_client, model, log=None):
    ...
    if log:
        log.step("intent", result=first_token, via="llm", ms=elapsed)

# 改动后
async def classify_intent(user_input, history, llm_client, model, hooks=None):
    ...
    if hooks:
        hooks.fire("intent", result=first_token, via="llm", ms=elapsed)
```

改动量：把 `log.step(` 替换为 `hooks.fire(`，参数 `log` 改为 `hooks`。纯机械替换。

#### 10.3.3 `orchestrator/engine.py` — Context 类型更新

```python
# 改动前
@dataclass
class OrchestratorContext:
    history: list[dict] = field(default_factory=list)
    tool_runner: Any = None
    llm_client: Any = None
    model: str = ""
    log: Any = None  # FlowLog

# 改动后
@dataclass
class OrchestratorContext:
    history: list[dict] = field(default_factory=list)
    tool_runner: Any = None
    llm_client: Any = None
    model: str = ""
    hooks: Any = None  # HookRegistry（替代 log）
```

#### 10.3.4 `orchestrator/state_machine.py` — 调用替换

```python
# 改动前
context.log.step("orch_plan", **step_data)
context.log.step("tool_exec", name=name, result=result[:100], ms=elapsed)

# 改动后
context.hooks.fire("orch_plan", **step_data)
context.hooks.fire("tool_exec", name=name, result=result[:100], ms=elapsed)
```

`orchestrator/langgraph_engine.py` 同理。

### 10.4 事件命名规范

保持当前 FlowLog 已有的事件名不变，确保 `/log` 命令的输出格式不受影响：

| 事件名 | 触发位置 | 数据字段 | 说明 |
|--------|---------|---------|------|
| `memory` | cli/app.py | `msgs`, `window`, `chars`, `context_window` | 记忆加载 |
| `intent` | router/intent.py | `result`, `via`, `ms` | 意图分类 |
| `complexity` | cli/app.py | `result` | 复杂度评估 |
| `router` | cli/app.py | `model`, `reason` | 模型路由 |
| `orch_plan` | orchestrator/ | `iter`, `tools`, `ms` | LLM 规划 |
| `tool_exec` | orchestrator/ | `name`, `result`, `ms` | 工具执行 |
| `persist` | cli/app.py | `saved` | 持久化 |

未来可扩展的事件（Hook 系统就绪后自然支持）：

| 事件名 | 用途 |
|--------|------|
| `pre_llm_call` | LLM 调用前，可用于添加上下文 |
| `post_llm_call` | LLM 调用后，可用于 token 统计 |
| `session_start` / `session_end` | 会话生命周期 |
| `error` | 统一错误上报 |

### 10.5 文件改动清单

| 文件 | 改动类型 | 改动量 |
|------|---------|--------|
| `infra/hooks.py` | **新增** | ~50 行 |
| `cli/app.py` | 修改 | ~10 行（初始化 hooks，替换 log 传递） |
| `router/intent.py` | 修改 | ~5 行（`log.step` → `hooks.fire`，参数名） |
| `orchestrator/engine.py` | 修改 | ~3 行（`log` → `hooks`） |
| `orchestrator/state_machine.py` | 修改 | ~5 行（`context.log` → `context.hooks`） |
| `orchestrator/langgraph_engine.py` | 修改 | ~5 行（同上） |
| `log/flow.py` | **不变** | 0 |
| `log/writer.py` | **不变** | 0 |
| `tests/test_flow_log.py` | 修改 | 适配 hooks 参数 |

### 10.6 性能影响评估

```
场景：一次完整的 _process() 调用，包含 ~7 次 log.step()

当前方式开销:
  7 × (dict 创建 + 时间格式化 + 列表 append) ≈ 7 × 5μs = 35μs

Hook 方式开销:
  7 × (dict.get + 空列表遍历 + log.step) ≈ 7 × (0.1μs + 5μs) = 35.7μs

差异: ~0.7μs = 0.0007ms

对比 LLM 调用: 500-3000ms
性能影响: < 0.0002%，完全可以忽略
```

### 10.7 向后兼容性

- `/log` 命令的输出格式**完全不变**，因为 FlowLog 的数据结构和 `finish()` 方法没有改动
- `tests/test_flow_log.py` 中直接测试 FlowLog 的测试**不需要改**，只有通过 OrchestratorContext 传递 log 的测试需要适配

### 10.8 未来扩展路径

Hook 系统就绪后，以下扩展自然水到渠成：

```
Hook 系统
├── FlowLog（已有，作为 hook 的一个监听者）
├── 权限检查 hook（pre_tool_use 时检查工具权限）
├── 外部通知 hook（tool_exec 后发送 Slack/邮件通知）
├── Token 统计 hook（post_llm_call 时累计 token 用量）
├── 输入修正 hook（pre_llm_call 时自动添加上下文）
└── 自定义审计 hook（记录所有操作到外部系统）
```

这就是把 FlowLog 建在 Hook 上的核心价值：**不只是改了个调用方式，而是为整个扩展体系打下地基**。
