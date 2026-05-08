# Memory System v2 设计

**Date:** 2026-05-08
**Status:** Draft

## Goal

重构 Brix 的 memory 系统，解决三个核心问题：
1. **Session 混淆**：当前所有对话历史堆积在单一 `data/memory.json`，新 session 也会加载全部历史
2. **无人格定义**：Agent 没有稳定的 personality，每次对话都是空白人格
3. **无用户记忆**：Agent 不记住关于用户的任何信息，无法提供个性化服务

目标架构：参考 Claude Code 的 memdir 系统，建立分层记忆体系——soul.md（人格）+ user.md（用户画像）+ session history（对话历史）+ background extraction（自动提取）+ auto-dream（定期整合）。

## Architecture

**核心设计原则：Memory 系统必须完全独立，可整体替换。**

数据文件与逻辑文件严格分离。`memory/` 下的 `.py` 文件是逻辑层，`memory/data/` 下是运行时数据。

Memory 系统通过 `MemoryProvider` Protocol 对外暴露接口，`cli/app.py` 只依赖 Protocol，不依赖具体实现。未来可直接替换为 openclaw 或其他 memory 实现，只需新实现满足同一 Protocol。

```
memory/
├── __init__.py            # 包入口，导出核心类
├── soul.py                # SoulManager — 加载/写入 soul.md
├── user.py                # UserMemoryManager — 加载/写入 user.md
├── session.py             # SessionManager — session CRUD、自动保存
├── extraction.py          # MemoryExtractor — background memory extraction
├── consolidation.py       # AutoDream — 定期记忆整合
├── strategy.py            # MemoryStrategy（重构）— context window 管理
├── storage.py             # 重构为 session-based storage
└── data/                  # 运行时数据（.gitignore）
    ├── soul.md            # Agent 人格定义
    ├── user.md            # 用户画像
    ├── MEMORY.md          # 记忆索引（自动生成）
    ├── .dream_state.json  # Auto-dream 状态
    ├── sessions/          # Session 对话历史
    │   ├── index.json     # Session 元数据索引
    │   └── session-{uuid}.json
    └── extracted/         # 提取的结构化记忆
```

## MemoryProvider Protocol

Memory 系统的对外接口。`cli/app.py` 和 `orchestrator/` 只依赖此 Protocol，不直接 import 任何 `memory/` 内部模块。

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class MemoryProvider(Protocol):
    """Memory system interface. Replaceable at any time."""

    def load_soul(self) -> str:
        """Load soul.md content for system prompt injection. Empty if not exists."""
        ...

    def load_user_memory(self) -> str:
        """Load user.md content for system prompt injection. Empty if not exists."""
        ...

    def soul_exists(self) -> bool:
        """Check if soul.md exists."""
        ...

    def user_memory_exists(self) -> bool:
        """Check if user.md exists."""
        ...

    def create_session(self) -> str:
        """Create a new empty session. Returns session ID."""
        ...

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the current session."""
        ...

    def save_session(self) -> None:
        """Save current session to disk."""
        ...

    def load_session(self, session_id: str) -> list[dict]:
        """Load a session's messages for resume. Returns message list."""
        ...

    def list_sessions(self) -> list[dict]:
        """List all sessions with metadata (id, title, created_at, updated_at, message_count)."""
        ...

    def get_context_messages(self, system_prompt: str) -> list[dict]:
        """Build the message list to send to LLM. New session = [system_prompt]. Resume = [system_prompt + history]."""
        ...
```

**使用方式**：

```python
# cli/app.py — 只依赖 Protocol
from memory import MemoryProvider

class BrixCLI:
    def __init__(self, config):
        # 通过工厂函数创建，不直接 import 具体类
        self._memory: MemoryProvider = create_memory_provider(config)
```

**替换方式**：

```python
# 未来替换为 openclaw memory
from memory_openclaw import OpenClawMemoryProvider

class BrixCLI:
    def __init__(self, config):
        self._memory: MemoryProvider = OpenClawMemoryProvider(config)
```

**工厂函数** (`memory/__init__.py`)：

```python
def create_memory_provider(config: dict) -> MemoryProvider:
    """Factory function. Change this line to swap memory system."""
    from .provider import BrixMemoryProvider
    return BrixMemoryProvider(config)
```

## Components

### 1. `memory/soul.py` — SoulManager

**职责**：加载/写入 `memory/data/soul.md`，注入 system prompt。

```python
class SoulManager:
    def __init__(self, data_dir: str = "memory/data"):
        self._path = os.path.join(data_dir, "soul.md")
        self._content: str = ""

    def load(self) -> str:
        """加载 soul.md 内容，返回格式化的 system prompt 片段。不存在返回空。"""
        ...

    def exists(self) -> bool:
        """检查 soul.md 是否存在"""
        ...

    def get_system_prompt_section(self) -> str:
        """返回注入 system prompt 的文本块"""
        ...
```

**行为**：
- 启动时读取 `memory/data/soul.md`，缓存内容
- 文件不存在时返回空字符串，不报错
- 内容原样注入 system prompt，不做任何修改
- 提供 CLI 命令 `/soul` 查看当前 soul 配置
- **不提供 write 接口**：soul.md 由 Agent 通过 FileWriteTool 直接写入

### 2. `memory/user.py` — UserMemoryManager

**职责**：加载/写入 `memory/data/user.md`，注入 system prompt。

```python
class UserMemoryManager:
    def __init__(self, data_dir: str = "memory/data"):
        self._path = os.path.join(data_dir, "user.md")
        self._content: str = ""

    def load(self) -> str:
        """加载 user.md 内容。不存在返回空。"""
        ...

    def exists(self) -> bool:
        """检查 user.md 是否存在"""
        ...

    def get_system_prompt_section(self) -> str:
        """返回注入 system prompt 的文本块"""
        ...
```

**行为**：
- 启动时读取 `memory/data/user.md`，缓存内容
- 文件不存在时返回空字符串，不报错
- 提供 CLI 命令 `/user` 查看当前用户记忆
- **不提供 write 接口**：user.md 由 Agent 通过 FileWriteTool 直接写入

### 3. `memory/session.py` — SessionManager（核心）

**职责**：管理 session 生命周期——创建、保存、加载、列表、恢复。

```python
class SessionManager:
    def __init__(self, sessions_dir: str = "memory/data/sessions"):
        self._dir = sessions_dir
        self._index_path = os.path.join(sessions_dir, "index.json")
        self._current_session: Session | None = None
        self._index: dict[str, SessionMeta] = {}

    def create_session(self) -> Session:
        """创建新 session，返回空 Session 对象"""
        ...

    def save_session(self, session: Session) -> None:
        """保存当前 session 到磁盘"""
        ...

    def load_session(self, session_id: str) -> Session:
        """加载指定 session（用于 resume）"""
        ...

    def list_sessions(self) -> list[SessionMeta]:
        """列出所有 session 元数据"""
        ...

    def delete_session(self, session_id: str) -> None:
        """删除指定 session"""
        ...

    def get_current_session(self) -> Session | None:
        """获取当前活跃 session"""
        ...

    def auto_save(self) -> None:
        """自动保存当前 session（每轮对话后调用）"""
        ...
```

**数据模型**：

```python
@dataclass
class SessionMeta:
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int

@dataclass
class Session:
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[dict]  # [{role, content, timestamp}, ...]
```

**Session 存储格式** (`memory/data/sessions/session-{uuid}.json`)：

```json
{
    "id": "a1b2c3d4",
    "title": "讨论 memory 系统重构",
    "created_at": "2026-05-08T10:30:00Z",
    "updated_at": "2026-05-08T11:45:00Z",
    "messages": [
        {"role": "user", "content": "...", "timestamp": "2026-05-08T10:30:00Z"},
        {"role": "assistant", "content": "...", "timestamp": "2026-05-08T10:30:05Z"}
    ]
}
```

**Session 索引** (`sessions/index.json`)：

```json
{
    "sessions": [
        {
            "id": "a1b2c3d4",
            "title": "讨论 memory 系统重构",
            "created_at": "2026-05-08T10:30:00Z",
            "updated_at": "2026-05-08T11:45:00Z",
            "message_count": 12
        }
    ]
}
```

**行为**：
- 每次启动 CLI 自动创建新 session（空对话）
- 每轮对话后自动保存当前 session
- Session title 由 Agent 在第一轮对话后自动生成（或取前 20 字符）
- `/resume` 命令列出最近 session，选择后加载到 context
- `/sessions` 命令列出所有 session
- `/clear` 命令清空当前 session（等同于创建新 session）

### 4. `memory/extraction.py` — MemoryExtractor

**职责**：在对话结束后，提取值得长期记忆的信息，更新 user.md 或 MEMORY.md。

```python
class MemoryExtractor:
    def __init__(self, user_memory: UserMemoryManager, llm_client: LLMClient):
        self._user_memory = user_memory
        self._llm = llm_client

    async def extract(self, session: Session) -> None:
        """分析 session 内容，提取值得记忆的信息"""
        ...
```

**行为**：
- 在 session 结束时（用户输入 `/quit` 或 idle timeout）触发
- 使用轻量 LLM（如 gpt-4.1-mini）分析最近对话
- 提取四类信息（参考 Claude Code 的 taxonomy）：
  - **user**：用户的角色、偏好、技术背景
  - **feedback**：用户对 Agent 行为的指导
  - **project**：正在进行的项目、目标
  - **reference**：外部系统/资源的指针
- 更新 `memory/data/user.md` 的对应 section
- 如果发现 project/reference 类信息，写入 `memory/data/extracted/` 目录

**Extraction Prompt**：

```
分析以下对话，提取值得长期记忆的信息。

对话内容：
{session_messages}

请识别：
1. 关于用户的信息（角色、偏好、技术背景、工作习惯）
2. 用户对 Agent 行为的反馈或指导
3. 正在进行的项目或任务
4. 外部系统、工具、资源的引用

输出格式（JSON）：
{
    "user": ["用户是数据科学家，主要用 Python"],
    "feedback": ["用户偏好简洁回复，不要总结"],
    "project": ["正在重构 Brix 的 memory 系统"],
    "reference": ["Linear 项目 BRIX 用于跟踪任务"]
}
```

### 5. `memory/consolidation.py` — AutoDream

**职责**：定期整合和清理记忆文件，保持记忆的时效性和一致性。

```python
class AutoDream:
    def __init__(self, data_dir: str = "memory/data", llm_client: LLMClient | None = None):
        self._dir = data_dir
        self._llm = llm_client
        self._state_path = os.path.join(data_dir, ".dream_state.json")

    async def should_run(self) -> bool:
        """检查是否满足整合条件"""
        ...

    async def consolidate(self) -> None:
        """执行记忆整合"""
        ...

    def _load_state(self) -> dict:
        """加载整合状态（上次整合时间、session 数量）"""
        ...

    def _save_state(self) -> None:
        """保存整合状态"""
        ...
```

**触发条件**（满足任一）：
- 距上次整合 >= 24 小时
- 自上次整合以来新增 >= 5 个 session
- 手动触发 `/dream` 命令

**整合流程**：
1. **Orient**：读取 `memory/data/MEMORY.md`、`memory/data/user.md`、`memory/data/soul.md`，了解当前记忆状态
2. **Gather**：扫描最近 session 的摘要，检查是否有过时信息
3. **Consolidate**：合并新信息到 `memory/data/user.md`，删除矛盾内容，转换相对时间为绝对时间
4. **Prune**：清理 `memory/data/extracted/` 中已整合的临时文件，更新 `memory/data/MEMORY.md` 索引

**状态文件** (`.dream_state.json`)：

```json
{
    "last_consolidation": "2026-05-08T10:00:00Z",
    "sessions_since_last": 3,
    "total_consolidations": 1
}
```

### 6. `memory/strategy.py` — MemoryStrategy（重构）

**职责**：管理 context window，构建 system prompt。内部模块，不暴露给外部。

```python
class MemoryStrategy:
    def __init__(self, max_context_tokens: int = 8000):
        self._max_tokens = max_context_tokens

    def build_system_prompt(
        self,
        soul: str,
        user_memory: str,
        soul_exists: bool,
        user_exists: bool,
        history: list[dict] | None = None,
    ) -> str:
        """构建完整的 system prompt，包含 onboarding / memory management 指令"""
        ...

    def get_context_window(self, history: list[dict], system_prompt: str) -> list[dict]:
        """构建发送给 LLM 的消息列表"""
        ...
```

**System Prompt 构建顺序**：

```
1. Soul Section（来自 soul.md，不存在则为空）
   ──── separator ────
2. User Memory Section（来自 user.md，不存在则为空）
   ──── separator ────
3. Onboarding 指令（仅当 soul 或 user 不存在时注入）
   ──── separator ────
4. Memory Management 指令（仅当 soul 和 user 都存在时注入）
   ──── separator ────
5. Session Context（仅 resume 时注入历史消息）
   ──── separator ────
6. Dynamic Context（日期、平台等）
```

**关键变化**：
- 新 session：只注入 soul + user + memory management 指令，**不注入对话历史**
- Resume session：注入 soul + user + memory management + 恢复的历史消息
- Onboarding：soul 或 user 不存在时注入 onboarding 指令替代 memory management 指令
- 移除 `should_save()` 的 `return True` 硬编码

### 7. `memory/storage.py` — 重构

**职责**：底层 JSON 文件读写，为 SessionManager 提供持久化。所有数据文件路径基于 `memory/data/`。

**改动**：
- 移除旧的 `MemoryStorage` 类（或重命名为内部实现）
- 新增 `SessionStorage`：负责单个 session JSON 文件的原子读写
- 新增 `IndexStorage`：负责 `index.json` 的读写
- 保留原子写入（tempfile + os.replace + fsync）机制
- 所有路径默认基于 `memory/data/`，确保数据与逻辑分离

### 8. `capability/tools/file_write.py` — FileWriteTool（新增）

**职责**：提供文件写入能力，让 Agent 能够创建和更新 memory 文件。

```python
class FileWriteTool(Tool):
    name = "file_write"
    description = "Write content to a file. Creates the file if it doesn't exist, overwrites if it does."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write to"},
            "content": {"type": "string", "description": "Content to write"}
        },
        "required": ["path", "content"]
    }

    async def execute(self, path: str, content: str) -> str:
        ...
```

**安全约束**：
- 只允许写入 `memory/data/` 目录下的文件（白名单路径）
- 写入其他路径需要用户确认（或直接拒绝）
- 原子写入：tempfile + os.replace + fsync

**注册**：在 `cli/app.py` 的 `_register_tools()` 中添加 `FileWriteTool()`。

### 9. `capability/tools/file_edit.py` — FileEditTool（新增）

**职责**：提供文件编辑能力，让 Agent 能够修改现有 memory 文件的特定部分。

```python
class FileEditTool(Tool):
    name = "file_edit"
    description = "Edit a file by replacing old_string with new_string. The old_string must be unique in the file."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to edit"},
            "old_string": {"type": "string", "description": "Text to replace"},
            "new_string": {"type": "string", "description": "Replacement text"}
        },
        "required": ["path", "old_string", "new_string"]
    }

    async def execute(self, path: str, old_string: str, new_string: str) -> str:
        ...
```

**安全约束**：同 FileWriteTool，只允许编辑 `memory/data/` 下的文件。

### 10. Onboarding — Agent 主动创建记忆文件

**触发条件**：启动时检测到 `memory/data/soul.md` 或 `memory/data/user.md` 不存在。

**实现方式**：System message 注入（不新增 intent 类型）。

**流程**：

```
CLI 启动
  → SoulManager.exists() / UserMemoryManager.exists()
  → 如果任一文件不存在：
      → 在 system prompt 末尾注入 onboarding 指令
      → Agent 收到指令后主动询问用户
      → Agent 使用 FileWriteTool 写入 soul.md / user.md
```

**注入的 System Message**：

```
## Onboarding Required

The following memory files are missing and need to be created:
{soul.md missing → "- soul.md: Your personality definition"}
{user.md missing → "- user.md: Your memory about the user"}

IMPORTANT: In your FIRST response, you MUST:
1. Introduce yourself naturally
2. Ask the user how they'd like to address you (your name)
3. Ask what they'd like to be called
4. Ask about their role/tech background (brief)
5. After gathering this info, use the file_write tool to create the missing files

For soul.md, write a personality definition based on the conversation tone.
For user.md, write what you've learned about the user.

Keep the conversation natural — this is a friendly introduction, not an interrogation.
```

**设计要点**：
- 不阻塞 REPL，通过 system message 让 Agent 在正常对话流中完成 onboarding
- Agent 自主决定问什么、怎么问，保持对话自然
- 用户回答后 Agent 调用 FileWriteTool 写入文件
- 写入完成后文件自动生效（下次 system prompt 构建时加载）

### 11. Memory-Aware System Prompt — 对话中自动更新记忆

**核心思路**：在 system prompt 中嵌入记忆管理指令，让 Agent 在对话过程中主动识别并更新记忆文件。不需要 intent 分类——Agent 本身就在处理对话内容，由它直接判断比额外的 LLM 分类调用更高效。

**注入的 System Prompt Section**（soul.md 和 user.md 都存在时注入）：

```
## Memory Management

You have persistent memory files:
- `memory/data/soul.md` — your personality definition (read-only in normal conversation)
- `memory/data/user.md` — what you know about the user

### When to update user.md:
Update user.md when the user EXPLICITLY shares:
- Name or how they want to be called
- Role, job title, or professional identity
- Tech stack, programming languages, tools they use
- Communication preferences (verbose/concise, language, formality)
- Current projects, goals, or priorities
- Feedback about your behavior ("don't do X", "I prefer Y")

Signaling phrases to watch for:
- "我是...", "我做...", "我用...", "我喜欢..."
- "I am...", "I work on...", "I use...", "I prefer..."
- "以后...", "不要...", "请...", "别..."
- Direct corrections to your behavior or assumptions

Use the file_edit tool to update specific sections. Don't overwrite the whole file.

### When NOT to update:
- Temporary information (current task details, debugging state)
- Information that belongs in session history, not long-term memory
- Speculative inferences — only record what the user explicitly stated
- Questions the user asks (questions ≠ statements of fact)

### Update pattern:
1. User shares info → acknowledge naturally ("了解了", "got it")
2. Call file_edit to update the relevant section in user.md
3. Continue the conversation — don't make a big deal about the update

### Soul.md is special:
- soul.md defines YOUR personality. Do not modify it unless the user explicitly asks.
- If the user wants to change your behavior/style, suggest they edit soul.md directly.
```

**设计要点**：
- 指令嵌入 system prompt，每次对话都生效
- Agent 自主判断何时更新，无需额外 intent 分类
- 列出具体的信号短语，降低 Agent 遗漏的概率
- user.md 可由 Agent 主动更新，soul.md 仅在用户明确要求时修改
- 使用 FileEditTool（而非 FileWriteTool）进行增量更新，避免覆盖
- M8 的 MemoryExtractor 作为兜底：对话结束时再扫描一遍，捕获 Agent 遗漏的信息

### 12. CLI 命令扩展

| 命令 | 功能 |
|------|------|
| `/soul` | 查看当前 soul.md 内容 |
| `/user` | 查看当前 user.md 内容 |
| `/sessions` | 列出最近 10 个 session |
| `/resume [id]` | 恢复指定 session（无 id 时交互选择） |
| `/clear` | 清空当前 session，开始新对话 |
| `/dream` | 手动触发记忆整合 |
| `/export` | 导出当前 session 为 markdown |
| `/log` | 保持不变，显示当前 session 的 FlowLog |

### 13. `cli/app.py` — 启动流程重构

**当前流程**（问题）：
```
启动 → 加载 memory.json 全部历史 → 每轮都塞进 context
```

**新流程**：
```
启动 → 创建新 Session
     → 检查 soul.md / user.md 是否存在
     → 加载 soul.md → 注入 system prompt（不存在则注入 onboarding 指令）
     → 加载 user.md → 注入 system prompt（不存在则注入 onboarding 指令）
     → 注入 memory management 指令（文件都存在时）
     → context = [system_prompt]（无历史）
     → 等待用户输入

首次对话 → Agent 主动介绍自己、询问用户信息
         → Agent 调用 FileWriteTool 写入 soul.md / user.md
         → 后续 system prompt 自动包含新内容

用户输入 → 处理 → 保存到当前 session → 自动保存
         → 如果 Agent 判断需要更新 user.md → 调用 FileEditTool

/resume → 选择 session → 加载 session 历史
        → context = [system_prompt + 恢复的历史]
        → 继续对话

/quit → 触发 memory extraction → 保存 session → 退出
```

## Data Flow

### 首次启动（Onboarding）

```
CLI 启动
  → SessionManager.create_session() — 新空 session
  → SoulManager.exists() = False
  → UserMemoryManager.exists() = False
  → MemoryStrategy.build_system_prompt(
        soul="", user="",
        onboarding=["soul.md missing", "user.md missing"]
    ) — 构建 system prompt + onboarding 指令
  → context = [system_prompt + onboarding 指令]

用户输入 "你好"
  → Agent 根据 onboarding 指令主动介绍自己
  → Agent: "你好！我是 Brix，你的个人 AI 助手。怎么称呼你？"
  → 用户: "叫我 kuicao 就行"
  → Agent: "好的 kuicao！你希望我叫什么名字？"
  → 用户: "你就叫 Brix 吧"
  → Agent 调用 FileWriteTool("memory/data/soul.md", "...")
  → Agent 调用 FileWriteTool("memory/data/user.md", "...")
  → 后续对话中 system prompt 自动包含 soul + user 内容
```

### 新 Session（正常启动，文件已存在）

```
CLI 启动
  → SessionManager.create_session() — 新空 session
  → SoulManager.load() — 读取 memory/data/soul.md
  → UserMemoryManager.load() — 读取 memory/data/user.md
  → MemoryStrategy.build_system_prompt(soul, user) — 构建 system prompt
  → context = [system_prompt, 无历史]

用户输入 "帮我写个函数"
  → SessionManager.add_message("user", input)
  → MemoryStrategy.get_context_window([], system_prompt) — 只有 system prompt
  → Orchestrator 处理
  → SessionManager.add_message("assistant", response)
  → SessionManager.auto_save() — 写入 memory/data/sessions/session-{id}.json
```

### 对话中更新记忆

```
用户: "我是做后端开发的，主要用 Go 和 Python"
  → Agent 识别到用户信息，判断应更新 user.md
  → Agent 调用 FileEditTool("memory/data/user.md",
        "## Tech Stack\n- [to be learned]",
        "## Tech Stack\n- Go (primary)\n- Python (secondary)")
  → Agent: "了解了，Go + Python 后端开发。我记下了。"
  → 后续对话 system prompt 自动包含更新后的 user.md
```

### Resume Session

```
用户输入 /resume
  → SessionManager.list_sessions() — 显示最近 session
  → 用户选择 session-a1b2c3d4
  → SessionManager.load_session("a1b2c3d4") — 加载历史
  → MemoryStrategy.build_system_prompt(soul, user, history) — system prompt + 历史
  → context = [system_prompt, 恢复的历史消息]

用户输入 "继续上次的工作"
  → 正常对话流程，历史已在 context 中
```

### Memory Extraction（对话结束时）

```
用户输入 /quit
  → SessionManager.save_session()
  → MemoryExtractor.extract(session)
      → LLM 分析对话内容
      → 提取 user/feedback/project/reference 信息
      → 更新 memory/data/user.md 对应 section
  → 退出
```

### Auto-Dream（后台定期）

```
启动时检查 memory/data/.dream_state.json
  → if should_run():
      → AutoDream.consolidate()
          → 读取 memory/data/user.md, memory/data/MEMORY.md
          → 扫描最近 session 摘要
          → 合并/清理/更新记忆文件
          → 更新 memory/data/.dream_state.json
```

## Error Handling

- **soul.md 不存在**：注入 onboarding 指令，Agent 主动询问并创建
- **user.md 不存在**：注入 onboarding 指令，Agent 主动询问并创建
- **session 文件损坏**：log warning，创建新 session
- **index.json 损坏**：扫描 sessions/ 目录重建索引
- **extraction 失败**：log warning，不影响 session 保存
- **consolidation 失败**：log warning，不影响正常使用
- **FileWriteTool 写入失败**：返回错误信息给 Agent，Agent 告知用户
- **磁盘写入失败**：原子写入机制保证不会损坏已有文件
- **memory/data/ 目录不存在**：storage 层自动创建目录

## Testing Strategy

### 新增 `tests/test_memory_v2.py`

**SoulManager**：
- 加载存在的 soul.md
- soul.md 不存在时返回空字符串
- exists() 正确判断
- system prompt section 格式正确

**UserMemoryManager**：
- 加载存在的 user.md
- user.md 不存在时返回空字符串
- exists() 正确判断
- system prompt section 格式正确

**SessionManager**：
- create_session() 生成有效 UUID 和时间戳
- save_session() / load_session() 数据一致性
- list_sessions() 按更新时间倒序
- delete_session() 同时删除文件和索引
- auto_save() 每 N 轮自动触发
- index.json 与 session 文件的一致性

**MemoryExtractor**：
- extract() 正确解析 LLM 输出
- 更新 user.md 的对应 section
- LLM 返回无效 JSON 时的容错

**AutoDream**：
- should_run() 时间条件
- should_run() session 数量条件
- consolidate() 正确合并记忆
- 状态文件读写

**MemoryStrategy**：
- 新 session 只有 soul + user，无历史
- resume session 包含历史
- Onboarding 指令注入正确（文件缺失时）
- Memory management 指令注入正确（文件存在时）
- token budget 正确应用

### 新增 `tests/test_file_tools.py`

**FileWriteTool**：
- 写入新文件成功
- 覆盖已有文件成功
- 拒绝写入 memory/data/ 外的路径
- 原子写入（不损坏已有文件）

**FileEditTool**：
- 替换唯一字符串成功
- old_string 不唯一时报错
- 拒绝编辑 memory/data/ 外的路径

### 不变量验证

- 所有现有测试通过
- `/log` 命令行为不变
- 新启动不加载 `data/memory.json`

## File Change Summary

| 文件 | 改动 | 量 |
|------|------|-----|
| `memory/__init__.py` | **重写** | ~30行（Protocol + 工厂函数） |
| `memory/provider.py` | **新增** | ~100行（BrixMemoryProvider 实现） |
| `memory/soul.py` | **新增** | ~40行 |
| `memory/user.py` | **新增** | ~60行 |
| `memory/session.py` | **新增** | ~150行 |
| `memory/extraction.py` | **新增** | ~80行 |
| `memory/consolidation.py` | **新增** | ~100行 |
| `memory/strategy.py` | **重写** | ~80行 |
| `memory/storage.py` | **重构** | ~60行 |
| `memory/data/` | **新增目录** | 运行时数据（.gitignore） |
| `capability/tools/file_write.py` | **新增** | ~50行 |
| `capability/tools/file_edit.py` | **新增** | ~50行 |
| `capability/runner.py` | **不变** | 0 |
| `cli/app.py` | **重构** | ~60行改动 |
| `cli/commands.py` | **新增/修改** | ~60行 |
| `tests/test_memory_v2.py` | **新增** | ~200行 |
| `tests/test_memory.py` | **废弃或合并** | - |
| `config/settings.yaml` | **修改** | memory 配置更新 |
| `.gitignore` | **修改** | 添加 `memory/data/` |
| `CLAUDE.md` | **新增/修改** | 添加 memory 模块化约束 |

## Out of Scope

- Embedding-based memory retrieval（向量搜索）
- 多用户/团队记忆共享
- Session 分支（tree-structured conversations）
- 记忆文件的版本控制
- 外部记忆源（Notion、Obsidian 等集成）
- `data/memory.json` 的迁移（直接废弃）

## Milestones

### Milestone 7: Memory System v2 — 基础框架

**目标**：Session 隔离 + soul/user 加载 + Onboarding + 对话中自动更新记忆

**范围**：
- `memory/__init__.py`（MemoryProvider Protocol + 工厂函数）
- `memory/soul.py` + `memory/user.py` + `memory/session.py` + `memory/storage.py` + `memory/strategy.py`
- `memory/provider.py`（BrixMemoryProvider 实现 MemoryProvider Protocol）
- `memory/data/` 目录结构（.gitignore）
- `capability/tools/file_write.py` + `capability/tools/file_edit.py`
- Onboarding system message 注入
- Memory-aware system prompt 注入
- `cli/app.py` 启动流程重构（依赖 MemoryProvider Protocol）
- CLI 命令：`/sessions`, `/resume`, `/clear`, `/soul`, `/user`
- 测试覆盖

**验收标准**：
- 首次启动：Agent 主动介绍自己、询问用户信息、写入 soul.md + user.md
- 后续启动：加载 soul.md + user.md 到 system prompt，不加载历史
- 对话中 Agent 识别到用户信息时自动更新 user.md
- 对话自动保存到 `memory/data/sessions/`
- `/sessions` 列出历史 session
- `/resume` 恢复指定 session
- `/clear` 开始新 session
- `/soul` 显示 soul.md 内容
- `/user` 显示 user.md 内容
- 所有现有测试通过

### Milestone 8: Memory System v2 — 智能记忆

**目标**：Background extraction + auto-dream 整合

**范围**：
- `memory/extraction.py`（MemoryExtractor）
- `memory/consolidation.py`（AutoDream）
- CLI 命令：`/dream`, `/export`
- Extraction trigger 在 `/quit` 时
- Auto-dream 在启动时检查

**验收标准**：
- `/quit` 后 user.md 自动更新（如果对话中有值得记忆的信息）
- `/dream` 手动触发整合
- 启动时检查是否需要整合
- 整合后 MEMORY.md 索引更新
