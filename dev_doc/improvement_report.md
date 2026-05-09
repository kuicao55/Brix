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
| 终端 UI | print() 无格式 | React/Ink 双缓冲 + Markdown + 动画 | crossterm + Markdown 渲染 + Spinner |
| 上下文管理 | 字符数截断 (4000 字) | 多层压缩 (auto/micro/snip/collapse) | Token 阈值自动压缩 |
| 扩展机制 | 子类化 Tool | Hooks + Plugins + Skills + MCP | Hooks + MCP + 自定义命令 |
| 配置 | 单 YAML 文件 | 多层级合并 (全局/项目/本地/CLI/env) | 三层 JSON 合并 |
| 权限系统 | 文件读取有路径检查 | 完整分级权限 + 规则匹配 | 分级权限 + 交互式确认 |
| 部署 | pip install | npm 全局安装 | cargo build 单二进制 |

**核心判断**：Brix 的 7 层架构骨架设计良好，但缺少"血肉"——流式体验、上下文智能管理、扩展钩子、终端交互美化这四个日常助手最关键的能力。下面按优先级分层给出改进方案。

---

## 二、P0 — 必须优先改进（影响日常使用体验）

### 2.1 流式输出 (Streaming Output) ✅ 已完成

> **实现位置**: `cli/stream_renderer.py` — `StreamRenderer` + `_MarkerMarkdown`，`infra/providers/openai_compat.py` + `anthropic_compat.py` — `chat_stream()`，`orchestrator/state_machine.py` — `run_stream()`
> **集成状态**: `cli/app.py` 全链路流式 — 从 API SSE → 文本增量 → Safe Boundary 渲染 → 实时 Markdown 输出

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

**实际完成内容**：
- `infra/providers/openai_compat.py` — `chat_stream()` SSE 流式
- `infra/providers/anthropic_compat.py` — `chat_stream()` Anthropic 流式
- `orchestrator/state_machine.py` — `run_stream()` 流式编排循环
- `cli/stream_renderer.py` — Safe Boundary 检测 + Rich Live 实时渲染 + `_MarkerMarkdown` 内联标记
- `cli/app.py` — `_process_streaming()` 全链路流式消费

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

### 2.3 LLM 调用重试与错误处理 ⏳ 待实现

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

### 3.2 Skill / 快捷命令系统 ⏳ 待实现

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

### 3.3 层级化配置系统 ⏳ 待实现

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

### 4.1 MCP (Model Context Protocol) 支持 ⏳ 待实现

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

### 4.2 工具并发执行 ⏳ 待实现

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

### 4.3 System Prompt 动态组装 ⏳ 待实现

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

### 4.4 权限系统 ⏳ 待实现

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

### 5.1 用 AsyncGenerator 重写 Orchestrator ✅ 已完成

> **实现位置**: `orchestrator/state_machine.py` — `run_stream()` + `orchestrator/engine.py` — Protocol `run_stream()`



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

### 5.2 解决 `OrchestratorContext` 中的 `Any` 类型 ⏳ 待实现

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

### 5.3 工具自动发现 ⏳ 待实现

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
| 终端 UI 框架 (React/Ink) | Python 生态用 Rich 就够，不需要引入重框架（见第十一节 Rich 方案） |
| MCP Server 模式 | Brix 是客户端，不需要暴露为 MCP Server |
| 企业级权限 (MDM/策略) | 个人助手不需要 |
| 多语言 (Rust) 重写 | Python 开发效率高，Brix 不追求极致性能 |

---

## 七、推荐实施路线图

```
Phase 1 — 体验提升 (2-3 周)
├── [P0] 流式输出 + 实时 Markdown 渲染 — StreamRenderer + engine.run_stream  ✅
├── [P0] Spinner 进度指示器 — cli/spinner.py  ✅
├── [P0] Token 计数 — 替换 MemoryStrategy  ⏳
├── [P0] LLM 重试 — 添加指数退避  ⏳
├── [P1] 工具执行状态面板 — cli/tool_display.py  ✅
├── [P1] 启动 Banner — cli/banner.py  ✅
├── [P1] Markdown 渲染主题 — cli/theme.py  ✅
└── [P1] 层级化配置 — 改 ConfigLoader  ⏳

Phase 2 — 扩展性基础 (1-2 周)
├── [P1] Hook 系统 — hooks/registry.py  ✅
├── [P1] Skill 系统 — 新增 capability/skill.py  ⏳
├── [P2] 工具自动发现 — 改 capability/runner.py  ⏳
└── [P2] System Prompt 动态组装  ⏳

Phase 3 — 健壮性 (1 周)
├── [P2] 上下文智能压缩 — AutoCompactor  ⏳
├── [P2] 工具并发执行  ⏳
├── [P2] 权限系统  ⏳
├── [P2] 状态报告格式化 — cli/status_display.py  ⏳
├── [P2] 错误友好展示 — cli/error_display.py  ⏳
└── [P2] 类型安全改进  ⏳

Phase 4 — 生态接入 (2 周+)
├── [P2] MCP 客户端 (stdio)  ⏳
├── 更多内置工具 (日历、邮件、笔记等)  ⏳
└── Web 入口 (FastAPI + WebSocket)  ⏳
```

---

## 八、关键文件改动清单

| 文件 | 改动内容 | 优先级 | 状态 |
|------|----------|--------|------|
| `infra/llm_client.py` | 添加 stream 方法 + retry 逻辑 | P0 | ⏳ |
| `infra/providers/openai_compat.py` | 实现 SSE 流式 | P0 | ✅ |
| `infra/providers/anthropic_compat.py` | 实现 Anthropic 流式 | P0 | ✅ |
| `orchestrator/engine.py` | 协议增加 `run_stream` | P0 | ✅ |
| `orchestrator/state_machine.py` | 实现流式执行 | P0 | ✅ |
| `memory/strategy.py` | Token 计数替代字符计数 | P0 | ⏳ |
| `cli/stream_renderer.py` | 流式 Markdown 渲染器 + `_MarkerMarkdown` 内联标记 | P0 | ✅ |
| `cli/spinner.py` | Braille 点动画 Spinner | P0 | ✅ |
| `cli/stage_indicator.py` | **新增**：统一加载 spinner (update in-place) | P0 | ✅ |
| `cli/tool_display.py` | 工具执行状态面板 + ⏺/⎿ 标记 | P1 | ✅ |
| `cli/theme.py` | Brix 终端主题 (Rich Theme) | P1 | ✅ |
| `cli/banner.py` | 启动 ASCII Banner | P1 | ✅ |
| `cli/status_display.py` | **新增**：状态报告格式化 | P2 | ⏳ |
| `cli/error_display.py` | **新增**：友好错误展示 | P2 | ⏳ |
| `memory/compaction.py` | 新增：自动压缩 | P1 | ⏳ |
| `config/loader.py` | 层级化配置加载 | P1 | ⏳ |
| `hooks/registry.py` | Hook 注册与执行 | P1 | ✅ |
| `capability/skill.py` | 新增：Skill 注册与加载 | P1 | ⏳ |
| `capability/runner.py` | 工具自动发现 + 并发执行 | P2 | ⏳ |
| `cli/app.py` | 适配流式输出 + Spinner + 标记 + Skill 命令 | P0/P1 | ✅ |

---

## 九、总结

Brix 的 7 层架构骨架是好的——Protocol/ABC 的抽象、YAML 配置驱动、FlowLog 可观测性都体现了良好的设计品味。核心差距在于：

1. **没有流式输出** — 这是日常助手最大的体验短板
2. **上下文管理太简单** — 字符截断无法支撑长对话
3. **缺少 Hook 机制** — 扩展需要改核心代码
4. **终端交互空白** — 没有 Markdown 渲染、Spinner、工具状态面板，体验粗糙

这四个问题解决后，Brix 就具备了一个实用日常助手的基础能力。后续的 Skill 系统、MCP 支持、工具自动发现则是让 Brix 从"能用"变成"好用"的关键。

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

---

## 十一、终端美化与交互体验改进方案

> 基于对 Claude Code (TypeScript + 自定义 Ink 框架) 和 Claw Code (Rust + crossterm) 的终端 UI 实现的深入分析，
> 结合 Brix 的 Python 技术栈，设计适合 Rich 生态的终端美化方案。

### 11.1 两个项目的终端 UI 架构对比

| 维度 | Claude Code | Claw Code | Brix (当前) |
|------|------------|-----------|-------------|
| UI 框架 | 自定义 Ink (React + Yoga flexbox) | crossterm (裸 ANSI) | print() 无格式 |
| 渲染模式 | 双缓冲 + 帧差分 + 60fps | 直接写 stdout | 无 |
| Markdown 渲染 | marked.lexer + highlight.js + LRU 缓存 | pulldown-cmark + syntect | 无 |
| Spinner | React 动画组件 + 闪烁检测 | Braille 点帧动画 | 无 |
| 流式显示 | Ink dirty-node 增量更新 | MarkdownStreamState 安全边界检测 | 无 |
| 工具状态 | 动画点 + 进度消息 + 分类器徽章 | 盒子绘制面板 + emoji 图标 | 无 |
| 主题系统 | 6 套主题 80+ 颜色键 | ColorTheme 硬编码 | 无 |
| 代码高亮 | highlight.js (异步 Suspense) | syntect (base16-ocean.dark) | 无 |
| 输入编辑 | 自定义 TextInput + Vim 模式 | rustyline (Emacs 模式) | input() |

**核心判断**：Claude Code 的 React/Ink 方案虽然强大但对 Brix 过重；Claw Code 的 crossterm 裸写方案灵活但维护成本高。Brix 应走 **Rich 库**路线——Python 生态最成熟的终端 UI 库，兼顾表现力和开发效率。

### 11.2 技术选型：Rich 库

```toml
# pyproject.toml
[project]
dependencies = [
    "rich>=13.0",       # 终端 UI 核心
    "rich-live>=1.0",   # 实时刷新 (Rich 内置)
]
```

Rich 提供的核心能力：
- **Live Display**：实时刷新区域，类似 Claude Code 的双缓冲
- **Markdown 渲染**：内置 Markdown → ANSI，支持代码块、表格、列表
- **Syntax 高亮**：基于 Pygments，支持 300+ 语言
- **Progress / Spinner**：多种动画样式
- **Panel / Table / Tree**：结构化布局组件
- **主题系统**：可自定义 Style

### 11.3 流式输出 + 实时 Markdown 渲染 ✅ 已完成

> **实现位置**: `cli/stream_renderer.py` — `StreamRenderer` + `_MarkerMarkdown` (内联标记 + 续行缩进)

**现状问题**：Brix 等待 LLM 完整返回后一次性显示，无流式体验。

**参考实现**：
- Claude Code：Ink 的 dirty-node 增量更新，只重绘变化的子树
- Claw Code：`MarkdownStreamState` 缓冲 token，检测安全边界（完整代码块围栏、空行）后才渲染，防止不完整 Markdown 破坏显示

**改进方案**：

```python
# cli/stream_renderer.py — 新增
from rich.live import Live
from rich.markdown import Markdown
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
import re

class StreamRenderer:
    """流式输出渲染器，借鉴 Claw Code 的 MarkdownStreamState 设计"""

    def __init__(self, console: Console):
        self.console = console
        self.pending = ""
        self.rendered = ""
        self.live: Live | None = None

    def start(self):
        self.live = Live(
            console=self.console,
            refresh_per_second=15,  # 15fps 足够流畅，节省 CPU
            transient=False,        # 保留历史输出
        )
        self.live.start()

    def push_delta(self, delta: str):
        """接收 token 增量，检测安全边界后渲染"""
        self.pending += delta
        boundary = self._find_safe_boundary(self.pending)
        if boundary is not None:
            ready = self.pending[:boundary]
            self.pending = self.pending[boundary:]
            self.rendered += ready
            self._update_display()

    def flush(self):
        """流结束，渲染剩余内容"""
        if self.pending:
            self.rendered += self.pending
            self.pending = ""
            self._update_display()
        if self.live:
            self.live.stop()

    def _find_safe_boundary(self, text: str) -> int | None:
        """
        借鉴 Claw Code 的 find_stream_safe_boundary：
        等待完整代码块围栏 (```) 或空行，避免渲染不完整的 Markdown
        """
        lines = text.split('\n')
        in_fence = False
        last_safe = 0

        for i, line in enumerate(lines):
            if line.strip().startswith('```'):
                in_fence = not in_fence
                if not in_fence:
                    # 代码块闭合，这是安全点
                    pos = sum(len(l) + 1 for l in lines[:i + 1])
                    last_safe = pos
            elif not in_fence and line.strip() == '' and i > 0:
                # 空行且不在代码块内，也是安全点
                pos = sum(len(l) + 1 for l in lines[:i + 1])
                last_safe = pos

        if last_safe > 0:
            return last_safe
        return None

    def _update_display(self):
        if self.live:
            md = Markdown(self.rendered)
            self.live.update(md)
```

**在 CLI 中集成**：

```python
# cli/app.py — 改造 _process 方法
async def _process(self, user_input: str) -> str:
    renderer = StreamRenderer(self.console)
    renderer.start()

    try:
        async for chunk in engine.run_stream(ctx):
            if isinstance(chunk, str):
                renderer.push_delta(chunk)
            elif isinstance(chunk, dict) and chunk.get("type") == "tool_call":
                renderer.flush()
                self._display_tool_call(chunk)
    finally:
        renderer.flush()
```

**工作量**：2-3 天（StreamRenderer + engine.run_stream 改造）
**收益**：流式输出 + 实时 Markdown 渲染，体感速度提升 3-5 倍

### 11.4 Markdown 终端渲染 ✅ 已完成

> **实现位置**: `cli/theme.py` — `BRIX_THEME` (Rich Theme, markdown.* + tool.* + spinner.* + stage.* 样式)



**参考实现**：
- Claude Code：`marked.lexer` 解析 + `highlight.js` 语法高亮 + LRU 缓存 (500 条)
- Claw Code：`pulldown-cmark` 解析 + `syntect` (base16-ocean.dark) + 暗色背景 `\x1b[48;5;236m`

**Rich 内置方案**（零额外开发）：

```python
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.console import Console

console = Console()

# 直接渲染 Markdown（内置代码块高亮、表格、列表、引用）
md = Markdown("""
# 标题

这是一个 **粗体** 和 *斜体* 的示例。

```python
def hello():
    print("Hello, Brix!")
```

| 列1 | 列2 |
|-----|-----|
| A   | B   |
""")
console.print(md)
```

**增强：自定义 Markdown 渲染样式**

```python
# cli/theme.py — 新增
from rich.theme import Theme
from rich.style import Style

BRIX_THEME = Theme({
    "markdown.h1": Style(bold=True, color="cyan"),
    "markdown.h2": Style(bold=True, color="bright_white"),
    "markdown.h3": Style(color="blue"),
    "markdown.code": Style(color="green"),
    "markdown.code_block": Style(bgcolor="grey11"),
    "markdown.link": Style(color="blue", underline=True),
    "markdown.em": Style(italic=True, color="magenta"),       # 借鉴 Claw Code
    "markdown.strong": Style(bold=True, color="yellow"),       # 借鉴 Claw Code
    "markdown.blockquote": Style(color="grey50"),              # 借鉴 Claw Code
    "tool.border": Style(color="grey50"),
    "tool.name": Style(bold=True, color="cyan"),
    "tool.success": Style(color="green"),
    "tool.error": Style(color="red"),
    "spinner.active": Style(color="blue"),
    "spinner.done": Style(color="green"),
    "spinner.failed": Style(color="red"),
})
```

**工作量**：1 天（主要是主题微调）
**收益**：代码块、表格、列表在终端中美观可读

### 11.5 Spinner 与进度指示器 ✅ 已完成

> **实现位置**: `cli/spinner.py` — `Spinner` (Braille 动画 + stop/finish/fail)，`cli/stage_indicator.py` — `StageIndicator` (统一 spinner，update in-place)



**参考实现**：
- Claude Code：React `SpinnerGlyph` 组件，120ms 帧率，`['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']` Braille 点动画，带闪烁检测和 stall 检测（颜色从主题色渐变到 `rgb(171,43,63)`），还有 token 计数器平滑递增动画
- Claw Code：`Spinner` 结构体，10 帧 Braille 点，`SavePosition/RestorePosition` 原地覆盖，`tick/finish/fail` 三方法生命周期

**改进方案**：

```python
# cli/spinner.py — 新增
import sys
import time
import threading
from rich.console import Console
from rich.text import Text
from rich.live import Live

BRAILLE_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

class Spinner:
    """借鉴 Claude Code + Claw Code 的 Spinner 设计"""

    def __init__(self, console: Console, label: str = "Thinking..."):
        self.console = console
        self.label = label
        self.frame_idx = 0
        self.start_time = time.time()
        self.running = False
        self.live: Live | None = None
        self._thread: threading.Thread | None = None

    def _render_frame(self) -> Text:
        elapsed = time.time() - self.start_time
        frame = BRAILLE_FRAMES[self.frame_idx % len(BRAILLE_FRAMES)]
        text = Text()
        text.append(f"  {frame} ", style="spinner.active")
        text.append(self.label, style="dim")
        text.append(f"  {elapsed:.1f}s", style="dim cyan")  # 借鉴 Claude Code 的计时
        return text

    def start(self):
        self.running = True
        self.start_time = time.time()
        self.live = Live(self._render_frame(), console=self.console,
                         refresh_per_second=10, transient=True)
        self.live.start()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def _animate(self):
        while self.running:
            self.frame_idx += 1
            if self.live:
                self.live.update(self._render_frame())
            time.sleep(0.1)

    def finish(self, label: str = "Done"):
        self.running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        if self.live:
            self.live.stop()
        elapsed = time.time() - self.start_time
        self.console.print(f"  [green]✔[/] {label}  [dim]{elapsed:.1f}s[/]")

    def fail(self, label: str = "Failed"):
        self.running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        if self.live:
            self.live.stop()
        elapsed = time.time() - self.start_time
        self.console.print(f"  [red]✘[/] {label}  [dim]{elapsed:.1f}s[/]")

    def update_label(self, label: str):
        self.label = label
```

**工作量**：1 天
**收益**：LLM 思考、工具执行时有动画反馈，不再"空白等待"

### 11.6 工具执行状态面板 ✅ 已完成

> **实现位置**: `cli/tool_display.py` — `ToolDisplay` (Panel 面板 + ⏺/⎿ 标记 + 颜色状态)



**参考实现**：
- Claude Code：`ToolUseLoader` 组件，黑色圆点闪烁动画 (`useBlink`)，状态分 queued/in-progress/resolved/error，工具结果通过 `tool.renderToolResultMessage()` 渲染
- Claw Code：`format_tool_call_start` 函数，盒子绘制面板 `╭─ name ─╮ / │ detail / ╰──╯`，每种工具类型有自定义格式（bash 用暗色背景 `$ command`，edit 用红绿 diff 预览）

**改进方案**：

```python
# cli/tool_display.py — 新增
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.console import Console
from rich.table import Table
import json

class ToolDisplay:
    """工具执行状态展示，借鉴 Claw Code 的盒子绘制风格"""

    TOOL_ICONS = {
        "file_read": "📄",
        "file_write": "✏️",
        "file_edit": "📝",
        "bash": "⚡",
        "web_search": "🔎",
        "memory_read": "🧠",
        "memory_write": "🧠",
    }

    def __init__(self, console: Console):
        self.console = console

    def show_tool_start(self, tool_name: str, tool_input: dict):
        """工具开始执行 — 盒子面板"""
        icon = self.TOOL_ICONS.get(tool_name, "🔧")
        detail = self._format_tool_detail(tool_name, tool_input)

        panel = Panel(
            detail,
            title=f"[tool.name]{icon} {tool_name}[/]",
            title_align="left",
            border_style="tool.border",
            padding=(0, 1),
        )
        self.console.print(panel)

    def show_tool_result(self, tool_name: str, result: str, elapsed_ms: float,
                         is_error: bool = False):
        """工具执行完成 — 简洁结果行"""
        icon = self.TOOL_ICONS.get(tool_name, "🔧")
        status_style = "tool.error" if is_error else "tool.success"
        status_icon = "✘" if is_error else "✔"
        elapsed_str = f"{elapsed_ms:.0f}ms"

        # 截断过长结果
        preview = result[:200].replace('\n', ' ')
        if len(result) > 200:
            preview += "…"

        text = Text()
        text.append(f"  {icon} ", style="dim")
        text.append(f"{tool_name}", style="tool.name")
        text.append(f"  {status_icon}", style=status_style)
        text.append(f"  {elapsed_str}", style="dim cyan")
        if is_error:
            text.append(f"  {preview}", style="tool.error")

        self.console.print(text)

    def _format_tool_detail(self, tool_name: str, tool_input: dict) -> str:
        """按工具类型格式化详情"""
        if tool_name == "bash":
            cmd = tool_input.get("command", "")
            return f"[white on grey11]$ {cmd}[/]"  # 借鉴 Claw Code 暗色背景
        elif tool_name == "file_read":
            path = tool_input.get("path", "")
            return f"📄 Reading [link]{path}[/]"
        elif tool_name == "file_write":
            path = tool_input.get("path", "")
            content = tool_input.get("content", "")
            lines = content.count('\n') + 1
            return f"✏️ Writing [link]{path}[/] ({lines} lines)"
        elif tool_name == "file_edit":
            path = tool_input.get("path", "")
            old = tool_input.get("old_string", "")
            new = tool_input.get("new_string", "")
            # 借鉴 Claw Code 的 diff 预览
            diff_text = Text()
            for line in old.split('\n')[:3]:
                diff_text.append(f"- {line}\n", style="red")
            for line in new.split('\n')[:3]:
                diff_text.append(f"+ {line}\n", style="green")
            return f"📝 Editing [link]{path}[/]\n{diff_text.plain}"
        elif tool_name == "web_search":
            query = tool_input.get("query", "")
            return f"🔎 Searching: {query}"
        else:
            preview = json.dumps(tool_input, ensure_ascii=False)[:150]
            return preview
```

**工作量**：1-2 天
**收益**：工具执行过程可视化，用户知道 AI 在做什么、花了多久

### 11.7 启动 Banner 与状态展示 ✅ 已完成

> **实现位置**: `cli/banner.py` — `show_banner()` (Rich Table + ASCII art + model/cwd/version 信息)



**参考实现**：
- Claude Code：无 ASCII art，但启动时显示简洁的 model/permission/directory 信息
- Claw Code：大幅 ASCII art "CLAW Code" + 模型/权限/目录/会话信息，两列对齐格式

**改进方案**：

```python
# cli/banner.py — 新增
from rich.console import Console
from rich.text import Text
from rich.panel import Panel

BRIX_ASCII = r"""
[bold cyan] ██████╗ ██████╗ ██╗██╗  ██╗[/]
[bold cyan] ██╔══██╗██╔══██╗██║╚██╗██╔╝[/]
[bold cyan] ██████╔╝██████╔╝██║ ╚███╔╝ [/]
[bold cyan] ██╔══██╗██╔══██╗██║ ██╔██╗ [/]
[bold cyan] ██████╔╝██║  ██║██║██╔╝ ██╗[/]
[bold cyan] ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝[/]
"""

def show_startup_banner(console: Console, model: str, cwd: str,
                         permission: str = "full"):
    """启动 Banner，借鉴 Claw Code 的信息展示风格"""
    console.print(BRIX_ASCII)

    info = Text()
    info.append("  Model       ", style="dim")
    info.append(f"{model}\n", style="bold")
    info.append("  Directory   ", style="dim")
    info.append(f"{cwd}\n")
    info.append("  Permission  ", style="dim")
    info.append(f"{permission}\n")
    info.append("\n")
    info.append("  Type ", style="dim")
    info.append("/help", style="bold")
    info.append(" for commands", style="dim")
    info.append(" · ", style="dim")
    info.append("Ctrl+C", style="bold")
    info.append(" to exit", style="dim")

    console.print(info)
    console.print()
```

**工作量**：0.5 天
**收益**：启动时有品牌感，关键信息一目了然

### 11.8 状态报告格式化 ⏳ 待实现

**参考实现**：
- Claw Code：所有 slash 命令输出采用统一的两列对齐格式，标题 + 缩进键值对，session 列表用 `● current` / `○ saved` 标记
- Claude Code：`/status` 命令显示 model、permission、messages、tokens 等信息

**改进方案**：

```python
# cli/status_display.py — 新增
from rich.console import Console
from rich.table import Table
from rich.text import Text

class StatusDisplay:
    """统一的状态报告格式，借鉴 Claw Code 的两列对齐风格"""

    def __init__(self, console: Console):
        self.console = console

    def show_status(self, **kwargs):
        """通用状态展示"""
        for section_name, items in self._group_sections(kwargs).items():
            self.console.print(f"\n[bold]{section_name}[/]")
            for key, value in items.items():
                key_text = Text(f"  {key:<18}", style="dim")
                self.console.print(key_text, value)

    def show_session_list(self, sessions: list[dict], current_id: str):
        """会话列表，借鉴 Claw Code 的 ●/○ 标记"""
        self.console.print("\n[bold]Sessions[/]")
        for s in sessions:
            marker = "●" if s["id"] == current_id else "○"
            style = "bold green" if s["id"] == current_id else "dim"
            self.console.print(f"  [{style}]{marker}[/{style}] {s['name']}  "
                             f"[dim]{s['date']}[/]")
```

**工作量**：0.5 天
**收益**：`/status`、`/sessions` 等命令输出整齐美观

### 11.9 错误展示 ⏳ 待实现

**参考实现**：
- Claude Code：针对不同错误类型（上下文超限、API key 无效、余额不足、超时）有专门的友好提示，长错误支持 `Ctrl+O` 展开
- Claw Code：`spinner.fail()` 红色 `✘` 图标 + salmon red 文本 `\x1b[38;5;203m`

**改进方案**：

```python
# cli/error_display.py — 新增
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

ERROR_MESSAGES = {
    "context_limit": {
        "title": "Context Limit Reached",
        "hint": "Try /compact to reduce context, or start a new session.",
    },
    "rate_limit": {
        "title": "Rate Limited",
        "hint": "Waiting and retrying automatically...",
    },
    "api_timeout": {
        "title": "API Timeout",
        "hint": "Check your network connection. You can increase timeout via config.",
    },
    "api_key_invalid": {
        "title": "Invalid API Key",
        "hint": "Check your API key in settings or environment variables.",
    },
}

def show_error(console: Console, error_type: str, detail: str = ""):
    """友好错误展示，借鉴 Claude Code 的分类提示"""
    info = ERROR_MESSAGES.get(error_type, {"title": "Error", "hint": ""})

    text = Text()
    text.append(f"✘ {info['title']}\n", style="bold red")
    if detail:
        # 截断长错误
        preview = detail[:300] + ("…" if len(detail) > 300 else "")
        text.append(f"\n{preview}\n", style="dim")
    if info.get("hint"):
        text.append(f"\n💡 {info['hint']}", style="yellow")

    panel = Panel(text, border_style="red", padding=(0, 1))
    console.print(panel)
```

**工作量**：0.5 天
**收益**：错误信息友好可操作，不再是冰冷的 traceback

### 11.10 改进优先级与文件清单

| 改进项 | 优先级 | 工作量 | 新增/修改文件 | 状态 |
|--------|--------|--------|--------------|------|
| 流式输出 + 实时 Markdown 渲染 | P0 | 2-3 天 | `cli/stream_renderer.py` (新), `cli/app.py` (改), `infra/providers/*.py` (改) | ✅ |
| Spinner 进度指示器 | P0 | 1 天 | `cli/spinner.py` (新), `cli/stage_indicator.py` (新), `cli/app.py` (改) | ✅ |
| 工具执行状态面板 | P1 | 1-2 天 | `cli/tool_display.py` (新), `orchestrator/state_machine.py` (改) | ✅ |
| Markdown 渲染主题 | P1 | 1 天 | `cli/theme.py` (新), `cli/app.py` (改) | ✅ |
| 启动 Banner | P1 | 0.5 天 | `cli/banner.py` (新), `cli/app.py` (改) | ✅ |
| 响应标记 (⏺/⎿) | P1 | 0.5 天 | `cli/stream_renderer.py` (改), `cli/tool_display.py` (改), `cli/app.py` (改) | ✅ |
| 状态报告格式化 | P2 | 0.5 天 | `cli/status_display.py` (新) | ⏳ |
| 错误友好展示 | P2 | 0.5 天 | `cli/error_display.py` (新) | ⏳ |

**依赖关系**：
```
流式输出 (P0) ──depends on──> LLM Client stream 方法 (P0)
Spinner (P0) ──independent──> 可立即实现
工具面板 (P1) ──depends on──> Hook 系统 (已完成) + Spinner
Markdown 主题 (P1) ──depends on──> 流式输出
启动 Banner (P1) ──independent──> 可立即实现
状态报告 (P2) ──independent──> 可立即实现
错误展示 (P2) ──independent──> 可立即实现
```

**建议实施顺序**：Spinner → 启动 Banner → 流式输出 → 工具面板 → Markdown 主题 → 状态报告 → 错误展示

### 11.11 对路线图的影响

将终端美化纳入路线图后，Phase 1 更新为：

```
Phase 1 — 体验提升 (2-3 周)
├── [P0] 流式输出 + 实时 Markdown 渲染 — StreamRenderer + engine.run_stream  ✅
├── [P0] Spinner 进度指示器 — cli/spinner.py + cli/stage_indicator.py  ✅
├── [P0] Token 计数 — 替换 MemoryStrategy  ⏳
├── [P0] LLM 重试 — 添加指数退避  ⏳
├── [P1] 工具执行状态面板 — cli/tool_display.py  ✅
├── [P1] 启动 Banner — cli/banner.py  ✅
├── [P1] Markdown 渲染主题 — cli/theme.py  ✅
├── [P1] 响应标记 — ⏺/⎿ 内联标记 + 颜色状态  ✅
└── [P1] 层级化配置 — 改 ConfigLoader  ⏳
```

---

## 十二、工具调用期间 Spinner 空白问题 ✅ 已完成

> **发现日期**: 2026-05-08
> **严重程度**: 高 — 直接影响用户对"AI 在干什么"的感知

### 12.1 问题描述

当 Agent 的文本响应结束后、工具调用开始执行前，终端没有任何视觉反馈。用户看到的是：

```
  ⏺ 好了，让我把这些信息记下来——        ← 文本渲染结束，StreamRenderer 停止
                                          ← 空白！没有任何动画！持续数秒
╭─ ✏️ file_write ────────────────────────╮  ← 工具面板突然出现
│ ✏️ Writing soul.md (25 lines)
╰─────────────────────────────────────────╯
```

这个"空白期"发生在 LLM 完成文本生成、开始生成 tool_call 参数的过程中，通常持续 1-3 秒。用户不知道 AI 在做什么，体验很差。

### 12.2 根因分析

问题出在 `cli/app.py` 的 `_process_streaming()` 方法（第 275-395 行）的事件处理逻辑：

```python
# 当前代码（简化）
async for event in self._orchestrator.run_stream(user_input, context):
    if event_type == "text_delta":
        if renderer is None:
            indicator.finish()          # ← Spinner 在这里被终止！
            renderer = StreamRenderer(...)
            renderer.start()
        renderer.push_delta(text)

    elif event_type == "tool_call":
        indicator.finish()              # ← 此时 indicator 早已 finish，这是空操作
        if renderer is not None:
            renderer.flush()
            renderer = None
        tool_display.show_tool_start(...)
```

**关键问题**：
1. 第一个 `text_delta` 到达时，`indicator.finish()` 被调用，Spinner 永久停止
2. 文本流结束后，LLM 开始生成 `tool_call` 的 JSON 参数（这部分由 `infra/providers/*.py` 的 `chat_stream()` 解析）
3. 在 `text_delta` 结束和 `tool_call` 事件到达之间，没有任何事件产生
4. 此时终端完全静默——Spinner 已停止，StreamRenderer 没有新内容，ToolDisplay 还没开始

### 12.3 参考实现

#### Claude Code 的方案

Claude Code 有 5 种 `SpinnerMode`：`requesting`、`responding`、`thinking`、`tool-use`、`tool-input`。

在 `src/utils/messages.ts` 的 `handleMessageFromStream` 中，模式切换非常频繁：
- `text_delta` 到达 → `responding` 模式（Shimmer 动画扫过动词文本）
- `tool_call` 开始 → `tool-use` 模式（正弦波脉冲动画，颜色在 messageColor 和 shimmerColor 之间交替）
- `tool_input` 增量到达 → `tool-input` 模式

关键：**Claude Code 的 Spinner 永远不会在文本流期间停止**。它只是切换模式。Spinner 只在整个 turn 结束时才停止。

#### Claw Code (Rust) 的方案

Claw Code 更简单但同样有效：
- 文本流期间：Spinner 保持活跃（虽然 label 不变）
- 工具调用时：Spinner 继续活跃，同时显示工具面板
- 整个 turn 结束时：`spinner.finish("✨ Done")`

### 12.4 改进方案

#### 方案 A：文本流期间保持 Spinner 活跃（推荐，最小改动）

**核心思路**：不要在第一个 `text_delta` 时终止 Spinner，而是在 `tool_call` 或流结束时才终止。

```python
# cli/app.py — _process_streaming() 改进
async for event in self._orchestrator.run_stream(user_input, context):
    event_type = event.get("type", "")

    if event_type == "text_delta":
        text = event.get("text", "")
        if text:
            if renderer is None:
                # 不再在这里 finish indicator！
                # indicator.finish()  ← 删除这行
                indicator.update("Responding")  # 更新 label 即可
                from rich.text import Text
                renderer = StreamRenderer(
                    self._console,
                    marker=Text("  ⏺ ", style="green"),
                )
                renderer.start()
            renderer.push_delta(text)
            content_parts.append(text)

    elif event_type == "tool_call":
        # 工具调用开始 — 此时才真正停止 spinner
        if renderer is not None:
            renderer.flush()
            renderer = None
        indicator.update("Tool")  # 显示 "Executing tool..."
        tool_name = event.get("name", "unknown")
        tool_display.show_tool_start(
            tool_name, event.get("input", {})
        )

    elif event_type == "tool_result":
        # 工具执行完成
        tool_name = event.get("name", "unknown")
        elapsed_ms = event.get("ms", 0)
        is_err = event.get("is_error", False)
        tool_display.show_tool_result(
            tool_name,
            event.get("result", ""),
            elapsed_ms,
            is_error=is_err,
        )
```

**问题**：这会导致 Spinner 和 StreamRenderer 同时输出到终端，产生冲突。因为两者都使用 Rich 的 `Live` display。

#### 方案 B：引入 ToolSpinner（推荐，干净的架构）

**核心思路**：在文本流和工具调用之间，用一个独立的轻量 Spinner 填充空白期。

```python
# cli/stage_indicator.py — 扩展

STAGE_LABELS = {
    "Memory": "Loading memory...",
    "Intent": "Classifying intent...",
    "Complexity": "Evaluating complexity...",
    "Route": "Selecting model...",
    "Planning": "Planning...",
    "Responding": "Generating response...",   # 新增
    "Tool": "Executing tool...",              # 新增
}

class StageIndicator:
    def __init__(self, console: Console, label: str = "Thinking...") -> None:
        self._spinner = Spinner(console, label=label)
        self._spinner.start()
        self._finished = False               # 新增：跟踪状态

    def update(self, stage: str) -> None:
        label = STAGE_LABELS.get(stage, "Working...")
        if not self._finished:               # 只有未 finish 时才更新
            self._spinner.update_label(label)

    def finish(self) -> None:
        if not self._finished:               # 防止重复 finish
            self._finished = True
            self._spinner.stop()

    def finish_with_label(self, label: str) -> None:
        """带标签的 finish，用于显示完成状态"""
        if not self._finished:
            self._finished = True
            self._spinner.finish(label)
```

然后在 `_process_streaming()` 中：

```python
# cli/app.py — 改进后的事件处理

# 1. 不在 text_delta 时 finish indicator
# 2. 在 tool_call 时用 indicator 显示 "Executing tool..."
# 3. 在流结束时才 finish indicator

async for event in self._orchestrator.run_stream(user_input, context):
    event_type = event.get("type", "")

    if event_type == "text_delta":
        text = event.get("text", "")
        if text:
            if renderer is None:
                # 第一个 text_delta — 不 finish indicator，只更新 label
                indicator.update("Responding")
                from rich.text import Text
                renderer = StreamRenderer(
                    self._console,
                    marker=Text("  ⏺ ", style="green"),
                )
                renderer.start()
            renderer.push_delta(text)
            content_parts.append(text)

    elif event_type == "tool_call":
        # 工具调用 — flush renderer，indicator 保持活跃
        if renderer is not None:
            renderer.flush()
            renderer = None
        indicator.update("Tool")
        tool_display.show_tool_start(
            event.get("name", "unknown"),
            event.get("input", {}),
        )

    elif event_type == "tool_result":
        tool_display.show_tool_result(
            event.get("name", "unknown"),
            event.get("result", ""),
            event.get("ms", 0),
            is_error=event.get("is_error", False),
        )
        # 工具执行完成，indicator 继续等待下一个 LLM 响应
        indicator.update("Planning")  # 回到 planning 状态

# 流结束 — 此时才 finish
if renderer is not None:
    renderer.flush()
indicator.finish()
```

**但是**：这里有一个架构冲突——`StreamRenderer` 使用 `Rich Live(transient=False)` 来保留输出，而 `StageIndicator` 使用 `Rich Live(transient=True)` 来实现消失效果。两者同时活跃会互相覆盖终端行。

#### 方案 C：StreamRenderer 内嵌 Spinner（最佳方案）

**核心思路**：让 `StreamRenderer` 自己管理一个内嵌的 Spinner 状态，当没有新内容时显示动画。

```python
# cli/stream_renderer.py — 扩展

class StreamRenderer:
    """流式输出渲染器，带内嵌 activity indicator"""

    def __init__(self, console: Console, marker: Text | None = None):
        self.console = console
        self.pending = ""
        self.rendered = ""
        self.live: Live | None = None
        self.marker = marker
        self._last_delta_time = 0.0        # 最后一次收到 delta 的时间
        self._show_indicator = False        # 是否显示 activity indicator

    def push_delta(self, delta: str):
        self.pending += delta
        self._last_delta_time = time.time()
        self._show_indicator = False        # 收到新内容，隐藏 indicator
        # ... 原有的 safe boundary 检测和渲染逻辑 ...

    def _render_content(self):
        """渲染内容，如果最近无新 delta 则显示 activity indicator"""
        parts = []
        if self.rendered:
            parts.append(Markdown(self.rendered))

        # 如果超过 0.5 秒没有新内容，显示 activity indicator
        if time.time() - self._last_delta_time > 0.5 and self.pending:
            frame = BRAILLE_FRAMES[int(time.time() * 10) % len(BRAILLE_FRAMES)]
            indicator = Text()
            indicator.append(f"\n  {frame} ", style="spinner.active")
            indicator.append("Waiting for tool call...", style="dim")
            parts.append(indicator)

        if self.live:
            self.live.update(Group(*parts) if parts else Text(""))
```

**这个方案最优雅**，但改动量较大，且需要处理 `StreamRenderer` 和 `StageIndicator` 的生命周期协调。

#### 方案 D：最小可行方案 — StageIndicator 延迟 finish（推荐实施）

**核心思路**：在第一个 `text_delta` 时不 finish `StageIndicator`，而是将其移到 `StreamRenderer.start()` 之后。当 `StreamRenderer` 接管输出后，`StageIndicator` 的 `Live(transient=True)` 会被 `StreamRenderer` 的 `Live(transient=False)` 自然覆盖。

实际上，经过仔细分析，`StageIndicator` 使用的是 `Live(transient=True)`，当它 stop 时会清除自己画的那行。而 `StreamRenderer` 使用的是 `Live(transient=False)`，它的输出会保留。两者不冲突——它们画的是不同的行。

**真正的问题是**：`indicator.finish()` 在第一个 `text_delta` 时被调用，导致 Spinner 消失。之后文本流可能持续几秒，然后 LLM 开始生成 tool_call 参数（又几秒），这段时间没有任何动画。

**最小改动方案**：

```python
# cli/app.py — _process_streaming() 最小改动

async for event in self._orchestrator.run_stream(user_input, context):
    event_type = event.get("type", "")

    if event_type == "text_delta":
        text = event.get("text", "")
        if text:
            if renderer is None:
                # 改动点：用 stop() 代替 finish()，不打印 "Done" 消息
                # 这样 Spinner 静默消失，不会干扰 StreamRenderer
                indicator._spinner.stop()  # 静默停止，不打印任何东西
                from rich.text import Text
                renderer = StreamRenderer(
                    self._console,
                    marker=Text("  ⏺ ", style="green"),
                )
                renderer.start()
            renderer.push_delta(text)
            content_parts.append(text)

    elif event_type == "tool_call":
        # 改动点：在工具调用前，如果 indicator 还活着，更新 label
        # 但实际上此时 indicator 已经 stop 了
        # 所以我们需要一个新机制来填补空白

        if renderer is not None:
            renderer.flush()
            renderer = None
        tool_display.show_tool_start(...)
```

**这仍然没有解决问题**——空白期依然存在。

### 12.5 最终推荐方案：StreamRenderer 内嵌 activity indicator

经过分析所有方案，**方案 C（StreamRenderer 内嵌 Spinner）** 是最佳方案，理由：

1. **不引入新的 UI 组件**——复用已有的 StreamRenderer
2. **生命周期自然**——StreamRenderer 在文本流开始时创建，在 tool_call 或流结束时销毁
3. **视觉连续**——用户看到的是同一个渲染区域，不会出现"Spinner 消失 → 空白 → 工具面板"的断裂感
4. **参考 Claude Code**——Claude Code 的 Spinner 就是内嵌在消息渲染组件中的，不是独立的全局 Spinner

#### 实现细节

```python
# cli/stream_renderer.py — 改进版

import time
from rich.live import Live
from rich.markdown import Markdown
from rich.console import Console
from rich.text import Text
from rich.group import Group

BRAILLE_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

class StreamRenderer:
    """流式输出渲染器，带内嵌 activity indicator 填充空白期。"""

    def __init__(self, console: Console, marker: Text | None = None) -> None:
        self.console = console
        self.pending = ""
        self.rendered = ""
        self.live: Live | None = None
        self.marker = marker
        self._last_delta_time = 0.0
        self._indicator_label = "Waiting for tool call..."

    def start(self) -> None:
        self._last_delta_time = time.time()
        self.live = Live(
            self._build_display(),
            console=self.console,
            refresh_per_second=10,
            transient=False,
        )
        self.live.start()

    def push_delta(self, delta: str) -> None:
        """接收 token 增量，检测安全边界后渲染。"""
        self.pending += delta
        self._last_delta_time = time.time()
        boundary = self._find_safe_boundary(self.pending)
        if boundary is not None:
            ready = self.pending[:boundary]
            self.pending = self.pending[boundary:]
            self.rendered += ready
            self._update_display()

    def flush(self) -> None:
        """流结束，渲染剩余内容。"""
        if self.pending:
            self.rendered += self.pending
            self.pending = ""
        self._update_display()
        if self.live:
            self.live.stop()

    def _build_display(self):
        """构建显示内容：已渲染的 Markdown + 可选的 activity indicator。"""
        parts = []
        if self.rendered:
            parts.append(Markdown(self.rendered))

        # 如果超过 0.8 秒没有新 delta，且有待渲染内容，显示 activity indicator
        # 这意味着 LLM 正在生成 tool_call 的 JSON 参数
        if (self.pending and
            time.time() - self._last_delta_time > 0.8):
            frame_idx = int(time.time() * 10) % len(BRAILLE_FRAMES)
            frame = BRAILLE_FRAMES[frame_idx]
            indicator = Text()
            indicator.append(f"\n  {frame} ", style="spinner.active")
            indicator.append(self._indicator_label, style="dim")
            parts.append(indicator)

        return Group(*parts) if parts else Text("")

    def _update_display(self) -> None:
        if self.live:
            self.live.update(self._build_display())

    def _find_safe_boundary(self, text: str) -> int | None:
        # ... 保持原有逻辑不变 ...
```

#### 配合 StageIndicator 的改动

```python
# cli/app.py — _process_streaming() 改进

# 构造 StageIndicator 时，不在 text_delta 时 finish
# 而是在 StreamRenderer 创建时静默 stop StageIndicator

async for event in self._orchestrator.run_stream(user_input, context):
    event_type = event.get("type", "")

    if event_type == "text_delta":
        text = event.get("text", "")
        if text:
            if renderer is None:
                # StageIndicator 静默消失（不打印 "Done"）
                indicator._spinner.stop()
                indicator._finished = True

                from rich.text import Text
                renderer = StreamRenderer(
                    self._console,
                    marker=Text("  ⏺ ", style="green"),
                )
                renderer.start()
            renderer.push_delta(text)
            content_parts.append(text)

    elif event_type == "tool_call":
        # StreamRenderer flush（会停止内嵌的 activity indicator）
        if renderer is not None:
            renderer.flush()
            renderer = None
        tool_display.show_tool_start(...)

    elif event_type == "tool_result":
        tool_display.show_tool_result(...)
        # 工具执行完成后，LLM 会开始新一轮的 text_delta
        # 如果下一轮有 text_delta，会创建新的 StreamRenderer

# finally
if renderer is not None:
    renderer.flush()
indicator.finish()
```

### 12.6 用户体验对比

**改进前**：
```
  ⏺ 好了，让我把这些信息记下来——
                                          ← 空白 1-3 秒
╭─ ✏️ file_write ────────────────────────╮
│ ✏️ Writing soul.md (25 lines)
╰─────────────────────────────────────────╯
```

**改进后**：
```
  ⏺ 好了，让我把这些信息记下来——
  ⠋ Waiting for tool call...              ← 活动指示器自动出现
╭─ ✏️ file_write ────────────────────────╮
│ ✏️ Writing soul.md (25 lines)
╰─────────────────────────────────────────╯
```

### 12.7 改动文件清单

| 文件 | 改动内容 | 改动量 |
|------|---------|--------|
| `cli/stream_renderer.py` | 添加 `_last_delta_time`、`_indicator_label`、`_build_display()` 方法，支持内嵌 activity indicator | ~30 行 |
| `cli/app.py` | 将 `indicator.finish()` 从第一个 `text_delta` 移到 StreamRenderer 创建时的 `indicator._spinner.stop()` | ~5 行 |
| `cli/stage_indicator.py` | 添加 `_finished` 状态跟踪，防止重复 finish | ~5 行 |

**工作量**：0.5 天
**收益**：消除工具调用前的空白期，用户体验显著提升

---

## 十三、Onboarding 问答深度不足 ✅ 已完成

> **发现日期**: 2026-05-08
> **严重程度**: 高 — 影响 user.md 和 soul.md 的质量，进而影响所有后续对话的个性化程度

### 13.1 问题描述

当前 `_ONBOARDING_TEMPLATE`（`memory/strategy.py` 第 9-25 行）指导 Agent 只问 3 个问题：

```
1. Introduce yourself
2. Ask what they'd like to be called (name)
3. Ask about their role/tech background (brief)
```

实际测试中，Agent 只问了称呼和角色就急着创建文件，导致：

**user.md 内容过于单薄**：
```markdown
# User - Ju老大
## 基本信息
- **称呼**：Ju老大
- **角色**：创业者 + 开发者
```

**soul.md 内容过于模板化**：
```markdown
# Soul - AI 助手性格定义
## 核心性格
- 友好且专业
- 高效直接
- 好奇心强
- 务实派
```

缺少的关键信息：
- **用户端**：年龄范围、性别、沟通语言偏好、技术水平细节、工作节奏、兴趣领域
- **Agent 端**：说话风格（幽默/严肃/毒舌）、人称（你/您）、回复长度偏好、是否有口头禅

### 13.2 参考分析：OpenClaw 的 Onboarding 设计

OpenClaw 的 `BOOTSTRAP.md` 设计了两个维度的问答：

**Agent 人格维度**（IDENTITY.md + SOUL.md）：
1. 你的名字 — 用户给 Agent 取名
2. 你的本质 — AI？机器人？精灵？
3. 你的气质 — 正式？随意？毒舌？温暖？
4. 你的标志 emoji

**用户画像维度**（USER.md）：
1. 用户的名字
2. 用户希望怎么被称呼
3. 代词（可选）
4. 时区
5. 备注 — 关心什么、在做什么、讨厌什么、什么让他们开心

OpenClaw 的核心理念：
- "Don't interrogate. Don't be robotic. Just... talk."（不要审讯，不要机械，就是聊天）
- "you're learning about a person, not building a dossier"（你在了解一个人，不是在建档案）
- Agent 有自主权决定怎么问、问多少

### 13.3 改进方案

#### 13.3.1 扩展 `_ONBOARDING_TEMPLATE`

```python
# memory/strategy.py — 改进版 _ONBOARDING_TEMPLATE

_ONBOARDING_TEMPLATE = """## Onboarding Required

The following memory files are missing and need to be created:
{soul_missing}{user_missing}

This is your FIRST conversation with this user. You need to learn about them
AND define your own personality. Take your time — don't rush to create files.

### Phase 1: Get to know each other (自然聊天，不要审讯)

Start by introducing yourself briefly, then learn about the user through conversation.
Ask these questions **one or two at a time**, in a natural conversational flow:

**About the user (for user.md):**
1. What should I call you? / 你希望我怎么称呼你？
2. What do you do? (role, industry, daily work) / 你是做什么的？
3. About how old are you? (rough range is fine, e.g., 20s, 30s) / 大概年纪？（范围就行）
4. What's your gender? (for better communication style) / 性别？（方便调整沟通方式）
5. What programming languages / tech stack do you use most? / 最常用的技术栈？
6. How do you prefer to communicate? (concise/detailed, casual/formal) / 沟通风格偏好？

**About yourself — define your personality (for soul.md):**
After learning about the user, propose a personality for yourself based on
their vibe. Ask them:
1. What kind of tone do you want from me? (direct, warm, witty, serious...) / 你希望我什么语气？
2. Should I be more like a colleague, a friend, or a professional assistant? / 同事/朋友/专业助手？
3. Any specific communication style? (e.g., "少废话直接给方案", "多解释为什么") / 具体沟通偏好？

### Phase 2: Create the files

After gathering enough information (at least 4-5 exchanges), use file_write to create:

**soul.md** — Your personality definition, including:
- Core personality traits (based on conversation tone)
- Communication style (language, tone, length, formality)
- Expertise areas
- Behavioral guidelines
- A characteristic phrase or greeting style that feels natural

**user.md** — What you know about the user, including:
- Basic info (name, preferred address, approximate age, gender)
- Background (role, industry, tech stack)
- Communication preferences (concise/detailed, language, formality)
- Personality notes (humor style, interests, work patterns)

### Guidelines:
- Keep it natural — this is a friendly introduction, not an interrogation
- Use the user's language — if they speak Chinese, respond in Chinese
- Don't ask all questions at once — 1-2 per turn, react to their answers
- It's OK to have fun with it — personality definition should feel collaborative
- You need AT LEAST 4 user responses before creating files
- When you propose your personality, let the user adjust it
"""
```

#### 13.3.2 扩展 user.md 模板

```markdown
# User - {name}

## 基本信息
- **称呼**：{preferred_name}
- **性别**：{gender}
- **年龄段**：{age_range}
- **角色**：{role}
- **行业**：{industry}

## 技术背景
- **主要技术栈**：{tech_stack}
- **技术水平**：{skill_level} (初学者/中级/高级/专家)
- **工作内容**：{daily_work}

## 沟通偏好
- **语言**：{language} (中文/英文/混合)
- **风格**：{style} (简洁直接/详细解释/轻松随意/正式专业)
- **回复长度**：{length} (尽量简短/适中/详细说明)

## 性格特点
- {personality_notes}

## 备注
- {additional_notes}
- 初次交流于 {date}
```

#### 13.3.3 扩展 soul.md 模板

```markdown
# Soul - {agent_name}

## 核心性格
- {trait_1}
- {trait_2}
- {trait_3}

## 沟通风格
- **语言**：{language}
- **语气**：{tone} (直接/温暖/幽默/毒舌/专业)
- **人称**：{pronoun} (你/您)
- **回复长度**：{length}
- **口头禅/特征表达**：{signature}

## 专长领域
- {expertise_1}
- {expertise_2}

## 行为准则
- {guideline_1}
- {guideline_2}
- {guideline_3}

## 与用户的关系定位
- {relationship} (同事/朋友/专业助手/导师)
```

#### 13.3.4 `_MEMORY_MGMT_TEMPLATE` 也需要更新

```python
# memory/strategy.py — 改进版 _MEMORY_MGMT_TEMPLATE（部分）

_MEMORY_MGMT_TEMPLATE = """## Memory Management

You have persistent memory files:
- `memory/data/soul.md` — your personality definition (read-only in normal conversation)
- `memory/data/user.md` — what you know about the user

### When to update user.md:
Update user.md when the user EXPLICITLY shares:
- Name or how they want to be called
- Age, gender, or demographic info
- Role, job title, or professional identity
- Tech stack, programming languages, tools they use
- Communication preferences (verbose/concise, language, formality)
- Current projects, goals, or priorities
- Feedback about your behavior ("don't do X", "I prefer Y")
- Personality traits, interests, work patterns

Signaling phrases to watch for:
- "我是...", "我做...", "我用...", "我喜欢...", "叫我..."
- "I am...", "I work on...", "I use...", "I prefer...", "call me..."
- "以后...", "不要...", "请...", "别...", "你能不能..."
- "太长了", "太啰嗦", "直接点", "详细说说"

Use the file_edit tool to update specific sections. Don't overwrite the whole file.

### When to update soul.md:
- User explicitly asks to change your personality or communication style
- User gives feedback like "你太正式了", "别那么客气", "说话直接点"
- Use file_edit to update specific sections

### When NOT to update:
- Temporary information (current task details, debugging state)
- Information that belongs in session history, not long-term memory
- Speculative inferences — only record what the user explicitly stated
"""
```

### 13.4 用户体验对比

**改进前**（实际测试结果）：
```
Agent: 你好！你希望我怎么称呼你？方便告诉我你的角色或技术背景吗？
User: 叫我Ju老大，我是一个创业者+开发者。
Agent: 好的！让我记下来——
       [创建 soul.md: 通用模板]
       [创建 user.md: 只有称呼和角色]
```

**改进后**（预期效果）：
```
Agent: 你好！我是你的 AI 助手，先认识一下——你希望我怎么称呼你？
User: 叫我Ju老大就行。
Agent: Ju老大好！你是做什么的？看你的工作内容我好调整我的风格。
User: 我是个创业者，也写代码，主要做 Python 和 Go。
Agent: 创业+开发，忙啊。方便问下大概年纪吗？（好决定用"你"还是"您"）
User: 30出头，用"你"就行。
Agent: 了解。那你希望我是什么风格？直接给方案不废话？还是多聊聊思路？
User: 直接点，别啰嗦，给方案就行。
Agent: 明白了。那我给自己定个风格：简洁直接，技术范儿，不废话。你觉得行吗？
User: 行，就这样。
Agent: 好，我来把这些都记下来——
       [创建 soul.md: 简洁直接、技术范儿、不废话、用"你"、中文为主]
       [创建 user.md: Ju老大、30出头、创业者+开发者、Python/Go、直接沟通风格]
```

### 13.5 改动文件清单

| 文件 | 改动内容 | 改动量 |
|------|---------|--------|
| `memory/strategy.py` | 重写 `_ONBOARDING_TEMPLATE`，扩展问答维度 | ~60 行 |
| `memory/strategy.py` | 更新 `_MEMORY_MGMT_TEMPLATE`，增加 soul.md 可更新条件 | ~15 行 |

**工作量**：0.5 天（纯 prompt 工程，不涉及代码架构改动）
**收益**：user.md 和 soul.md 信息量提升 3-5 倍，后续对话个性化程度显著提高

### 13.6 注意事项

1. **不要过度追问**：OpenClaw 的理念是"了解一个人，不是建档案"。年龄和性别是可选的，如果用户不想回答就跳过
2. **语言跟随用户**：如果用户用中文，所有问题都用中文
3. **Agent 人格应该是协商的**：Agent 提议 → 用户确认/调整，而不是 Agent 单方面决定
4. **至少 4 轮对话**：在创建文件前，确保有足够的信息交换
5. **Onboarding 后的首次使用**：创建文件后，Agent 应该自然地过渡到正常对话，而不是突然切换模式

---

## 十四、max_iterations 限制过严 ⚡ 最高优先级

> **发现日期**: 2026-05-08
> **严重程度**: 高 — 复杂任务（如多文件读取 + 编辑）会在第 5 次 LLM 调用后被截断，用户收到"I was unable to complete the request within the allowed steps"

### 14.1 问题描述

Brix 当前 `StateMachineOrchestrator.__init__` 中 `max_iterations=5`，计算的是 **每次 LLM 调用**（plan 阶段），而非单个工具调用。当 Agent 需要多次"读取→分析→编辑"循环时，5 次 LLM 调用很快耗尽。

**实际案例**：Agent 执行 5 个独立的 file_read，每次 LLM 调用带 1 个工具调用，第 5 次后触发 max_iterations 上限，任务被强制终止。

### 14.2 对比参考

| 项目 | max_iterations 策略 | 说明 |
|------|---------------------|------|
| Claude Code | 无限制（未定义上限） | 主 REPL 不设上限，依赖 token 预算自然终止 |
| Claw-code | `usize::MAX`（主循环），子 Agent 限制 32 | 主循环无限制，子 Agent 有安全上限 |
| Brix (当前) | 5 | 过于保守 |

### 14.3 解决方案

参考 Claude Code（无上限）和 Claw-code（`usize::MAX`）的做法：

1. 将默认 `max_iterations` 从 5 改为 **100**（安全兜底，防止无限循环，实际不会触及）
2. 对子 Agent（如果未来支持）限制为 32（与 Claw-code 一致）
3. 在 fallback 消息中加入已执行 iteration 数量，方便 debug

**工作量**：0.1 天（改一行默认值 + fallback 消息优化）
**收益**：消除复杂任务被截断的问题，用户体验显著提升

---

## 十五、工具执行期间无持续 Spinner ⚡ 最高优先级

> **发现日期**: 2026-05-08
> **严重程度**: 中 — 工具执行期间用户看到的是静态文本面板，缺少"AI 仍在工作"的动态反馈

### 15.1 问题描述

当前工具执行流程：
1. `tool_call` 事件 → 显示 `⏺ Calling tools...` + 工具面板
2. 工具执行中 → **无任何动态指示**
3. `tool_result` 事件 → 显示结果摘要

步骤 2 中用户看到的是静态面板，不知道工具是否仍在运行。对比 Claude Code 和 Claw-code：

| 项目 | 工具执行期间 Spinner 行为 |
|------|---------------------------|
| Claude Code | 模式切换 Spinner：requesting → responding → tool-use → thinking，每个阶段持续旋转 |
| Claw-code | per-tool Spinner：每个工具调用有自己的 Spinner（tick/finish/fail 生命周期） |
| Brix (当前) | 无 Spinner，静态面板 |

### 15.2 解决方案

借鉴 Claude Code 的**模式切换 Spinner** 设计：

1. 在 `ToolDisplay.show_tool_start()` 启动一个 Rich Live Spinner（Braille 动画）
2. Spinner 持续旋转直到 `show_tool_result()` 被调用
3. 使用 `threading` 或 `asyncio` 驱动 Spinner 动画，不阻塞工具执行
4. Spinner 文案统一为 `Calling tools...`（已实现的静态文案改为动态）

**关键实现细节**：
- `show_tool_start()` 创建 `Live` 上下文，启动 Spinner 线程
- `show_tool_result()` 停止 Spinner，打印最终结果
- 需要处理异常路径：工具抛出异常时 Spinner 也要正确停止

**工作量**：0.3 天
**收益**：工具执行期间有持续动态反馈，用户感知"AI 仍在工作"
