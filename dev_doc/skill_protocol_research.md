# Brix Skill 协议兼容方案研究报告

> 日期: 2026-05-12
> 目标: 为 Brix 引入类 Claude Code 的 Skill 协议，使 Agent 能够发现、加载和执行可复用的 prompt 工作流

---

## 一、Claude Code Skill 协议核心分析

### 1.1 Skill 的本质

Skill 是 **prompt-engineering-as-code**：将一段精心设计的 prompt + 元数据（何时使用、允许哪些工具、使用什么模型）封装为可复用单元。

与 Tool 的区别：
| 概念 | 本质 | 触发方式 | 实现形式 |
|------|------|---------|---------|
| **Tool** | 原子操作（读文件、执行 bash） | LLM 自主选择 | Python 类，实现 `execute()` |
| **Skill** | 声明式工作流（prompt + 权限 + 模型） | 用户 `/name` 或 LLM 通过 SkillTool 调用 | `SKILL.md` 文件 + YAML frontmatter |

### 1.2 Skill 的数据结构

Claude Code 中 Skill 是 `Command` 类型的一个变体（`type: 'prompt'`）。核心字段：

```typescript
// 必需字段
type: 'prompt'           // 标识这是一个 Skill
name: string             // 唯一标识符
description: string      // 人类可读描述
getPromptForCommand(args, context) -> ContentBlockParam[]  // 核心方法：返回 prompt 内容

// 关键可选字段
whenToUse?: string           // AI 匹配用的详细使用场景描述
allowedTools?: string[]      // Skill 执行期间允许使用的工具白名单
model?: string               // 模型覆盖（如 'opus', 'haiku'）
context?: 'inline' | 'fork' // 执行模式：内联注入当前会话 / fork 子 Agent
userInvocable?: boolean      // 用户是否可通过 /name 调用
disableModelInvocation?: boolean // 是否禁止 LLM 通过 SkillTool 调用
skillRoot?: string           // Skill 文件所在目录
```

### 1.3 Skill 的文件格式

采用 `skill-name/SKILL.md` 目录结构：

```
.claude/skills/
  commit/
    SKILL.md          # 主文件，含 YAML frontmatter + prompt 正文
    templates/         # 可选的资源文件
      commit_msg.md
```

`SKILL.md` 格式：
```markdown
---
name: commit
description: 提交代码变更
whenToUse: 当用户要求提交代码、创建 commit、保存变更时使用
allowedTools:
  - Bash
  - Read
model: haiku
---

# Commit Skill

请按以下步骤提交代码：

1. 运行 `git status` 查看变更
2. 运行 `git diff` 查看具体修改
3. 分析变更性质，编写 commit message
4. 执行 `git add` 和 `git commit`

$ARGUMENTS
```

### 1.4 Skill 的发现与加载

Claude Code 从 5 个来源并行加载 Skill：

1. **磁盘 Skill** — 扫描 `~/.claude/skills/` 和 `.claude/skills/` 目录
2. **内置 Skill** — 编译进 CLI 的 TypeScript 模块
3. **插件 Skill** — 从插件系统加载
4. **MCP Skill** — 通过 MCP 服务器的 `skill://` 资源
5. **遗留 Commands** — 旧的 `/commands/` 目录

### 1.5 Skill 的执行流程

两条调用路径，最终汇入同一处理逻辑：

**用户调用路径** (`/skill-name args`)：
1. 用户输入 → `processSlashCommand()` → 查找 Command
2. 判断 `context`:
   - `inline`（默认）→ 调用 `getPromptForCommand()` 获取 prompt → 注入当前会话为 meta UserMessage → LLM 继续处理
   - `fork` → 启动子 Agent 执行，结果返回主会话

**LLM 调用路径** (SkillTool)：
1. LLM 在 system-reminder 中看到 Skill 列表
2. LLM 调用 `Skill` 工具 → `SkillTool.call()` → 验证 → 权限检查 → 注入 prompt

**执行上下文修改（contextModifier）**：
- 合并 `allowedTools` 到工具白名单
- 覆盖模型（`model` 字段）
- 覆盖 effort 级别

### 1.6 变量替换机制

`getPromptForCommand()` 执行时支持变量替换：
- `${CLAUDE_SKILL_DIR}` → Skill 的根目录路径
- `${CLAUDE_SESSION_ID}` → 当前会话 ID
- `$ARGUMENTS` → 用户传入的参数
- `` !`shell command` `` → 执行 shell 命令并替换结果

---

## 二、Brix 现有架构分析

### 2.1 与 Skill 相关的现有组件

| 组件 | 文件 | 与 Skill 的关系 |
|------|------|----------------|
| `Tool` 基类 | `capability/base.py` | Skill 需要与 Tool 平行存在，但本质不同 |
| `ToolRunner` | `capability/runner.py` | Skill 执行时可能需要调用 Tool |
| `SlashCommand` 体系 | `capability/basics/commands.py` | 现有的 `/help`, `/quit` 等是硬编码命令，Skill 是动态可扩展的 |
| `OrchestratorEngine` | `orchestrator/engine.py` | Skill 执行需要通过 Orchestrator 的 plan/execute 循环 |
| `OrchestratorContext` | `orchestrator/engine.py` | Skill 需要访问 context 中的 tool_runner, llm_client 等 |
| `HookRegistry` | `hooks/registry.py` | Skill 可以注册自己的 hooks |
| `MemoryProvider` | `memory/__init__.py` | Skill 可能需要读写 memory |

### 2.2 现有 Slash Command 的局限

当前 `capability/basics/commands.py` 的命令是硬编码列表：
```python
COMMANDS = [
    {"name": "help", "description": "显示帮助"},
    {"name": "quit", "description": "退出"},
    # ...
]
```

这些命令在 `cli/app.py` 的 `_handle_command()` 中被硬编码分发。无法动态扩展。

### 2.3 架构约束（CLAUDE.md）

> 所有层通过 Protocol 接口通信，禁止跨层直接 import 内部模块。

这意味着：
1. Skill 系统必须通过 Protocol 与 Orchestrator、CLI、ToolRunner 交互
2. `capability/skill/` 目录需要定义自己的 Protocol
3. CLI 和 Orchestrator 通过 Protocol 调用 Skill，不直接 import Skill 实现

---

## 三、Skill 协议兼容方案设计

### 3.1 目录结构

```
capability/
  skill/
    __init__.py          # 导出 SkillProvider Protocol + 工厂函数
    base.py              # Skill 抽象基类
    loader.py            # 从磁盘加载 SKILL.md 文件
    registry.py          # Skill 注册表 + 发现机制
    executor.py          # Skill 执行器（inline 模式）
    builtin/             # 内置 Skill
      commit/
        SKILL.md
      review/
        SKILL.md
```

### 3.2 核心 Protocol 定义

```python
# capability/skill/base.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillMeta:
    """Skill 元数据，对应 SKILL.md 的 YAML frontmatter"""
    name: str                                    # 唯一标识符
    description: str                             # 人类可读描述
    when_to_use: str = ""                        # AI 匹配用描述
    allowed_tools: list[str] = field(default_factory=list)  # 工具白名单
    model: str | None = None                     # 模型覆盖
    context: str = "inline"                      # "inline" | "fork"
    user_invocable: bool = True                  # 用户可否 /name 调用
    disable_model_invocation: bool = False       # 是否禁止 LLM 调用
    skill_root: str = ""                         # Skill 文件目录
    arguments_hint: str = ""                     # 参数提示


class Skill(ABC):
    """Skill 抽象基类"""

    @property
    @abstractmethod
    def meta(self) -> SkillMeta:
        """返回 Skill 元数据"""
        ...

    @abstractmethod
    async def get_prompt(self, args: str, context: dict[str, Any]) -> str:
        """生成 Skill 的 prompt 内容

        Args:
            args: 用户传入的参数字符串
            context: 执行上下文，包含 session_id, skill_dir 等

        Returns:
            要注入会话的 prompt 文本
        """
        ...
```

### 3.3 SkillProvider Protocol（供 CLI 和 Orchestrator 使用）

```python
# capability/skill/__init__.py

from typing import Protocol, runtime_checkable
from .base import Skill, SkillMeta


@runtime_checkable
class SkillProvider(Protocol):
    """Skill 服务提供者协议，供 CLI 和 Orchestrator 调用"""

    def get_skill(self, name: str) -> Skill | None:
        """按名称查找 Skill"""
        ...

    def list_skills(self, include_hidden: bool = False) -> list[SkillMeta]:
        """列出所有可用 Skill 的元数据"""
        ...

    def get_skill_listing_text(self) -> str:
        """生成用于 system prompt 的 Skill 列表文本"""
        ...
```

### 3.4 SKILL.md 文件加载器

```python
# capability/skill/loader.py

import yaml
from pathlib import Path
from .base import Skill, SkillMeta


class FileSkill(Skill):
    """从 SKILL.md 文件加载的 Skill 实现"""

    def __init__(self, skill_dir: Path):
        self._skill_dir = skill_dir
        self._meta, self._prompt_template = self._parse(skill_dir / "SKILL.md")

    @property
    def meta(self) -> SkillMeta:
        return self._meta

    async def get_prompt(self, args: str, context: dict) -> str:
        prompt = self._prompt_template
        # 变量替换
        prompt = prompt.replace("${SKILL_DIR}", str(self._skill_dir))
        prompt = prompt.replace("$ARGUMENTS", args)
        if "session_id" in context:
            prompt = prompt.replace("${SESSION_ID}", context["session_id"])
        return prompt

    @staticmethod
    def _parse(path: Path) -> tuple[SkillMeta, str]:
        content = path.read_text(encoding="utf-8")
        # 解析 YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            frontmatter = yaml.safe_load(parts[1])
            prompt_body = parts[2].strip()
        else:
            frontmatter = {}
            prompt_body = content

        meta = SkillMeta(
            name=frontmatter.get("name", path.parent.name),
            description=frontmatter.get("description", ""),
            when_to_use=frontmatter.get("whenToUse", ""),
            allowed_tools=frontmatter.get("allowedTools", []),
            model=frontmatter.get("model"),
            context=frontmatter.get("context", "inline"),
            user_invocable=frontmatter.get("userInvocable", True),
            disable_model_invocation=frontmatter.get("disableModelInvocation", False),
            skill_root=str(path.parent),
            arguments_hint=frontmatter.get("argumentHint", ""),
        )
        return meta, prompt_body
```

### 3.5 Skill 注册表与发现

```python
# capability/skill/registry.py

from pathlib import Path
from .base import Skill, SkillMeta
from .loader import FileSkill
from . import SkillProvider


class SkillRegistry(SkillProvider):
    """Skill 注册表：发现、加载、查找"""

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.meta.name] = skill

    def get_skill(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_skills(self, include_hidden: bool = False) -> list[SkillMeta]:
        skills = self._skills.values()
        if not include_hidden:
            skills = [s for s in skills if s.meta.user_invocable or not s.meta.disable_model_invocation]
        return [s.meta for s in skills]

    def get_skill_listing_text(self) -> str:
        """生成 system prompt 中的 Skill 列表（供 LLM 发现和调用）"""
        lines = ["可用的 Skills:"]
        for meta in self.list_skills():
            line = f"- /{meta.name}: {meta.description}"
            if meta.when_to_use:
                line += f" ({meta.when_to_use})"
            lines.append(line)
        return "\n".join(lines)

    def discover_from_dir(self, skills_dir: Path) -> int:
        """从目录中发现并加载所有 SKILL.md"""
        count = 0
        if not skills_dir.is_dir():
            return count
        for entry in sorted(skills_dir.iterdir()):
            skill_file = entry / "SKILL.md"
            if entry.is_dir() and skill_file.is_file():
                try:
                    skill = FileSkill(entry)
                    self.register(skill)
                    count += 1
                except Exception:
                    pass  # 加载失败跳过，不阻塞
        return count
```

### 3.6 Skill 执行器

```python
# capability/skill/executor.py

from typing import Any
from .base import Skill
from ..runner import ToolRunner


class SkillExecutor:
    """执行 Skill：生成 prompt，注入会话上下文"""

    async def execute_inline(
        self,
        skill: Skill,
        args: str,
        context: dict[str, Any],
    ) -> str:
        """内联模式：返回要注入会话的 prompt 文本"""
        return await skill.get_prompt(args, context)

    async def execute_with_tool_filter(
        self,
        skill: Skill,
        args: str,
        context: dict[str, Any],
        tool_runner: ToolRunner,
    ) -> tuple[str, list[dict]]:
        """执行 Skill 并返回受限的工具 schema 列表

        Returns:
            (prompt_text, filtered_tool_schemas)
        """
        prompt = await skill.get_prompt(args, context)

        if skill.meta.allowed_tools:
            all_schemas = tool_runner.get_tool_schemas()
            allowed = set(skill.meta.allowed_tools)
            filtered = [s for s in all_schemas if s.get("function", {}).get("name") in allowed]
        else:
            filtered = tool_runner.get_tool_schemas()

        return prompt, filtered
```

### 3.7 CLI 集成点

`cli/app.py` 需要的改动：

1. **初始化阶段**：创建 `SkillRegistry`，扫描 `capability/skill/builtin/` 和用户自定义 Skill 目录
2. **命令补全**：将已注册 Skill 名称加入 `SlashCommandCompleter`
3. **命令分发**：`_handle_command()` 中，先查硬编码命令，再查 SkillRegistry
4. **LLM 集成**：将 `get_skill_listing_text()` 注入 system prompt，让 LLM 能发现和调用 Skill
5. **Skill 执行**：调用 `SkillExecutor.execute_inline()` 生成 prompt，注入当前会话

### 3.8 Orchestrator 集成点

`orchestrator/engine.py` 需要的改动：

`OrchestratorContext` 可选扩展（不破坏现有接口）：
```python
@dataclass
class OrchestratorContext:
    # ... 现有字段 ...
    skill_provider: Any = None  # SkillProvider 实例，可选
```

Orchestrator 本身不需要改动——Skill 的 prompt 在 CLI 层注入为普通用户消息后，Orchestrator 的 plan/execute 循环自然会处理其中的工具调用。

---

## 四、与 Claude Code 的差异与取舍

### 4.1 保留的功能

| 功能 | 说明 |
|------|------|
| SKILL.md 文件格式 | 兼容 frontmatter + prompt 正文结构 |
| 变量替换 | `$ARGUMENTS`, `${SKILL_DIR}`, `${SESSION_ID}` |
| 工具白名单 | `allowedTools` 限制 Skill 可用的工具 |
| 模型覆盖 | `model` 字段允许 Skill 指定特定模型 |
| 用户调用 + LLM 调用 | 双路径触发 |
| Skill 列表注入 system prompt | LLM 可发现可用 Skill |

### 4.2 暂不实现的功能（MVP 后可扩展）

| 功能 | 原因 |
|------|------|
| Fork 模式（子 Agent） | Brix 尚无子 Agent 机制，复杂度高 |
| MCP Skill 加载 | 需要先实现 MCP 客户端 |
| 远程 Skill | 依赖网络服务，MVP 阶段不需要 |
| Hooks 集成 | 可后续扩展，不影响核心流程 |
| 动态发现（路径触发） | 需要文件监控，优先级低 |
| Shell 命令替换 (`` !`...` ``) | 安全风险较高，MVP 阶段暂不支持 |
| 使用统计与推荐 | 可后续添加 |

### 4.3 Brix 特有的简化

1. **Python vs TypeScript**：Brix 用 Python 3.11+，类型系统更简洁
2. **Protocol 替代继承**：符合 Brix 的架构约束
3. **单用户场景**：不需要复杂的权限系统（Claude Code 有 5 层权限检查）
4. **内置 Skill 即文件**：不需要 TypeScript 编译，直接放 SKILL.md

---

## 五、实现路线图

### Phase 1: 基础框架（本次实现）

1. `capability/skill/base.py` — `SkillMeta` + `Skill` 抽象基类
2. `capability/skill/loader.py` — `FileSkill`（SKILL.md 解析 + 变量替换）
3. `capability/skill/registry.py` — `SkillRegistry`（注册 + 发现 + 列表）
4. `capability/skill/executor.py` — `SkillExecutor`（内联模式 + 工具过滤）
5. `capability/skill/__init__.py` — `SkillProvider` Protocol
6. `capability/skill/builtin/commit/SKILL.md` — 示例内置 Skill
7. CLI 集成 — 命令分发、补全、system prompt 注入
8. 测试

### Phase 2: 增强功能

- Fork 模式（子 Agent 隔离执行）
- Skill Hooks 集成
- Shell 命令替换（带沙箱）
- 使用统计

### Phase 3: 生态扩展

- MCP Skill 加载
- 远程 Skill 搜索
- Skill 自动生成（从会话中学习模式）

---

## 六、关键设计决策

### 6.1 为什么放在 `capability/skill/` 而不是新建顶层目录？

- Skill 本质上是一种"能力"，与 Tool 平行
- 遵循 CLAUDE.md 的模块化原则：通过 Protocol 对外暴露
- 不需要改动项目顶层结构

### 6.2 为什么选择 SKILL.md 而不是 Python 类定义？

- 降低 Skill 编写门槛：非程序员也能写 Skill
- 兼容 Claude Code 的 Skill 格式，可复用其生态
- Markdown 比 Python 代码更适合表达 prompt 模板

### 6.3 为什么不直接复用 Claude Code 的 SkillTool？

- Claude Code 的 SkillTool 是 TypeScript 实现，深度绑定其 Tool 系统
- Brix 的 Tool 体系（`Tool` 基类 + `ToolRunner`）是 Python Protocol
- 需要的是协议兼容（相同的 SKILL.md 格式、相同的语义），而非代码复用

---

## 七、参考文件清单

### Claude Code 关键文件

| 文件 | 关注点 |
|------|--------|
| `src/types/command.ts` | Command/PromptCommand 类型定义 |
| `src/skills/loadSkillsDir.ts` | SKILL.md 解析、变量替换、创建 SkillCommand |
| `src/skills/bundledSkills.ts` | BundledSkillDefinition、registerBundledSkill |
| `packages/.../SkillTool/SkillTool.ts` | Skill 调用入口：验证、权限、执行 |
| `src/commands.ts` | getSkills() 聚合多来源 Skill |
| `src/utils/processUserInput/processSlashCommand.tsx` | 用户 `/name` 调用分发 |
| `src/utils/attachments.ts` | Skill 列表注入 system prompt |

### Brix 关键文件

| 文件 | 需要修改 |
|------|---------|
| `capability/base.py` | 无需修改，作为参考 |
| `capability/runner.py` | 无需修改，Skill 执行器使用它 |
| `cli/app.py` | 集成 SkillRegistry + SkillExecutor |
| `cli/completer.py` | 扩展补全列表 |
| `orchestrator/engine.py` | OrchestratorContext 可选增加 skill_provider |
