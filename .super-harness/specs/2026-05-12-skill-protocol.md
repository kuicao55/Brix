# Brix Skill 协议设计规格

> 日期: 2026-05-12
> 状态: Brainstorm 完成，待规划

## 一、目标

为 Brix 引入类 Claude Code 的 Skill 协议，使 Agent 能够发现、加载和执行可复用的 prompt 工作流。

## 二、核心设计决策

### 2.1 统一 Command 抽象

采用 discriminated union 模式（参照 Claude Code），系统命令和 Skill 命令共享同一注册体系。

```python
class CommandType(Enum):
    SYSTEM = "system"   # 硬编码逻辑 (/quit, /clear)
    SKILL = "skill"     # prompt 注入 (/commit, /review)

@dataclass
class CommandMeta:
    name: str
    description: str
    type: CommandType
    when_to_use: str = ""
    user_invocable: bool = True
    disable_model_invocation: bool = False

class Command(ABC):
    @property
    @abstractmethod
    def meta(self) -> CommandMeta: ...

    @abstractmethod
    async def execute(self, args: str, context: CommandContext) -> CommandResult: ...
```

### 2.2 CommandResult 枚举返回值

```python
class CommandResultType(Enum):
    NONE = "none"       # 无后续操作
    QUIT = "quit"       # 退出 REPL
    CLEAR = "clear"     # 清空会话历史
    PROMPT = "prompt"   # 注入 prompt（Skill 专用）

@dataclass
class CommandResult:
    type: CommandResultType
    prompt_text: str = ""
    allowed_tools: list[str] | None = None
    model: str | None = None
```

### 2.3 单一 CommandRegistry

替代硬编码 if/elif 链 + 静态 COMMANDS 列表。所有命令（系统 + Skill）注册到同一处。

```python
class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None: ...
    def get(self, name: str) -> Command | None: ...
    def list_all(self) -> list[CommandMeta]: ...
    def get_skill_listing_text(self) -> str: ...
```

### 2.4 Skill 列表注入 system prompt

在 `_process_streaming()` 中轻量追加，不动 MemoryProvider 接口。

### 2.5 $ARGUMENTS 变量替换

- `$ARGUMENTS` → 完整参数字符串
- `$0`, `$1`, ... → 位置参数
- `${SKILL_DIR}` → Skill 文件目录
- `${SESSION_ID}` → 当前会话 ID
- 若 prompt 中无 `$ARGUMENTS` 占位符，自动追加

## 三、目录结构

```
capability/command/
    __init__.py          # Protocol 导出
    base.py              # CommandMeta, Command, CommandType, CommandResult, CommandContext
    registry.py          # CommandRegistry
    skill.py             # SkillCommand（包装 Skill，执行 prompt 注入）
    loader.py            # SKILL.md 文件加载器 + 变量替换
    builtin/
        __init__.py
        session.py       # /quit, /clear, /resume, /history
        info.py          # /help, /model, /soul, /user, /log
        skills/
            commit/
                SKILL.md # 示例内置 Skill
```

## 四、CLI 集成

### 4.1 命令分发

`cli/app.py` 的 `_handle_command()` 简化为：
1. 解析 `/name args`
2. `CommandRegistry.get(name)` 查找
3. `command.execute(args, context)` 执行
4. match `CommandResultType` 决定后续行为

### 4.2 补全器

`cli/completer.py` 的 `SlashCommandCompleter` 改为从 `CommandRegistry` 读取命令列表。

### 4.3 System Prompt 注入

`_process_streaming()` 中构建完 system prompt 后追加 Skill 列表。

## 五、受影响的现有文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `cli/app.py` | 重构 | 命令分发 + system prompt 注入 |
| `cli/completer.py` | 重构 | 从 CommandRegistry 读取 |
| `capability/basics/commands.py` | 废弃 | 被新 command 系统替代 |
| `orchestrator/engine.py` | 小改 | OrchestratorContext 可选增加字段 |

## 六、Phase 1 范围

1. `capability/command/base.py` — 核心类型定义
2. `capability/command/registry.py` — CommandRegistry
3. `capability/command/loader.py` — SKILL.md 加载器 + 变量替换
4. `capability/command/skill.py` — SkillCommand 实现
5. `capability/command/builtin/session.py` — 系统命令（quit/clear/resume/history）
6. `capability/command/builtin/info.py` — 系统命令（help/model/soul/user/log）
7. `capability/command/builtin/skills/commit/SKILL.md` — 示例 Skill
8. CLI 集成 — 命令分发 + 补全 + system prompt 注入
9. 测试

## 七、暂不实现（Phase 2+）

- Fork 模式（子 Agent 隔离执行）
- MCP Skill 加载
- Shell 命令替换
- Budget-aware 截断
- Skill Hooks 集成
- 使用统计
