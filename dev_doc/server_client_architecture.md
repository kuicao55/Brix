# Brix Server-Client 架构演进设计

> 版本: 1.0  
> 日期: 2026-06-26  
> 状态: 设计阶段 — 尚未实现

---

## 一、设计目标

将 Brix 从单一 TUI 进程重构为 **持久化后台 Server + 多前端 Client** 架构：

- **Server** 是常驻后台进程，承载所有核心逻辑（LLM 调用、Memory、Orchestrator、Tool、SideTask）
- **Client**（TUI / macOS 状态栏 / macOS 完整 GUI / Mobile）通过 WebSocket 连接 Server
- **关闭任何前端都不影响 Server 运行**，只有 `brix stop` 手动关闭
- **本地客户端**通过 Unix Domain Socket 连接（零网络开销），远程客户端通过 TCP WebSocket
- **语音硬件**（麦克风、扬声器）完全属于客户端，Server 不触碰任何音频设备
- **所有数据**仍以文件形式存储在 `memory/data/`

---

## 二、目标架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                     Brix Server (常驻后台进程)                      │
│                                                                  │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Memory   │  │ Orchestrator │  │  ToolRunner              │  │
│  │  Provider │  │ (StateMach)  │  │  + CommandRegistry       │  │
│  │  (文件锁)  │  │              │  │  + Skill 系统             │  │
│  └─────┬─────┘  └──────┬───────┘  └───────────┬──────────────┘  │
│        │               │                      │                 │
│  ┌─────┴───────────────┴──────────────────────┴──────────────┐  │
│  │                     BrixServerApp                          │  │
│  │  · 多 Session 并发管理 (per-connection MemoryProvider)       │  │
│  │  · SideTaskManager 统一调度                                 │  │
│  │  · LLMClient 统一管理 (含未来本地模型加载)                    │  │
│  │  · Hook 系统 + FlowLog                                     │  │
│  │  · PID 文件 + 信号处理 (SIGTERM 优雅关闭)                    │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                             │                                    │
│  ┌──────────────────────────┴─────────────────────────────────┐  │
│  │                   Transport Layer                           │  │
│  │  · Unix Domain Socket: ~/.brix/server.sock (本地, 高效)      │  │
│  │  · TCP WebSocket:     0.0.0.0:PORT (远程, 可选)             │  │
│  │  · 统一 JSON 消息协议，两种传输使用完全相同的协议               │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
└─────────────────────────────┼────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────────┐
          │                   │                       │
     ┌────┴─────┐      ┌──────┴──────┐        ┌──────┴──────┐
     │  TUI     │      │  macOS      │        │  Mobile     │
     │  Client  │      │  Status Bar │        │  Client     │
     │  (本地)  │      │  App (本地) │        │  (远程)     │
     │          │      │            │        │             │
     │ Unix     │      │ Unix       │        │ TCP         │
     │ Socket   │      │ Socket     │        │ WebSocket   │
     └──────────┘      └────────────┘        └─────────────┘
           ↑                  ↑
     ┌─────┴──────────────────┴─────┐
     │     语音硬件 (per-Client)     │
     │  · 麦克风 → VAD → STT        │
     │  · 扬声器 ← TTS              │
     │  (Server 不触碰音频设备)      │
     └──────────────────────────────┘
```

### 分层职责边界

| 层 | 拥有 | 不拥有 |
|---|------|--------|
| **Server** | Memory、LLMClient、ToolRunner、Orchestrator、CommandRegistry、SideTaskManager、HookRegistry、Skill、FlowLog、文件 I/O、PID 管理 | UI 渲染、终端输入输出、音频硬件、GUI 控件、进程间通信显示 |
| **Client** | 终端渲染(Rich/prompt_toolkit)、音频采集与播放(pyaudio/TTS/STT/VAD)、GUI 组件、OS 通知、菜单栏 | LLM 调用、memory 写入、tool 执行、session 文件管理、模型路由 |

---

## 三、通信协议

### 3.1 传输层

| 场景 | 传输 | 地址 |
|------|------|------|
| 本地 TUI、macOS App | Unix Domain Socket | `unix://~/.brix/server.sock` |
| 远程 Mobile | TCP WebSocket | `ws://HOST:PORT` (可升级为 WSS) |

两种传输使用 **完全相同的 WebSocket JSON 消息协议**，客户端只改连接地址。

### 3.2 消息类型定义

所有消息为 JSON，顶层字段 `type` 标识消息类型。

#### Client → Server

```jsonc
// ===== 核心交互 =====

// 发送聊天消息（触发 stream 响应）
{"type": "chat", "content": "帮我写一个排序函数"}

// 执行 slash 命令
{"type": "command", "command": "/resume"}
{"type": "command", "command": "/model", "args": "list"}
{"type": "command", "command": "/clear"}
{"type": "command", "command": "/quit"}          // 通知 server 保存并释放 session

// ===== 会话管理 =====

// 列出所有会话
{"type": "list_sessions"}

// 恢复指定会话
{"type": "resume_session", "session_id": "550e8400-e29b-..."}

// 创建新会话
{"type": "create_session"}

// ===== 状态查询 =====

// 获取 server 状态
{"type": "get_status"}

// ===== 语音桥接 =====

// 客户端完成 STT 后，将文本发送给 server
{"type": "voice_input", "content": "今天天气怎么样"}
```

#### Server → Client（流式事件 + 响应）

```jsonc
// ===== 聊天流式事件 =====

// 思考阶段（可选，取决于模型）
{"type": "thinking_delta", "text": "用户需要排序算法..."}

// 文本增量
{"type": "text_delta", "text": "这是一个快速排序实现"}

// 工具调用开始
{"type": "tool_call", "id": "call_abc123", "name": "read_file", "input": {"path": "src/main.py"}}

// 工具执行结果
{"type": "tool_result", "id": "call_abc123", "name": "read_file", "result": "def main():...", "ms": 42, "is_error": false}

// 流结束（一次 chat 完成）
{"type": "stream_end"}

// ===== 命令执行结果 =====

{"type": "command_result", "command": "/resume", "data": {
    "sessions": [{"id": "abc...", "title": "...", "message_count": 12}],
    "resumed_session_id": null
}}
{"type": "command_result", "command": "/model", "data": {"models": [...], "current": "..."}}
{"type": "command_result", "command": "/clear", "data": {"new_session_id": "def..."}}

// ===== 状态响应 =====

{"type": "status", "data": {
    "uptime_seconds": 3600,
    "model": "deepseek-v4-pro",
    "active_sessions": 3,
    "local_socket": "~/.brix/server.sock",
    "remote_port": null,
    "side_tasks": [{"name": "session_title", "running": false}]
}}

// ===== 错误 =====

{"type": "error", "message": "Model not found: unknown/model", "code": "MODEL_NOT_FOUND"}

// ===== Server 推送（广播给所有客户端） =====

{"type": "server_event", "event": "shutting_down", "data": {"reason": "user_requested"}}
```

### 3.3 协议实现

```python
# protocol/types.py — 共享类型定义

@dataclass
class ClientMessage:
    type: str                          # chat | command | list_sessions | resume_session | create_session | get_status | voice_input
    content: str = ""                  # chat / voice_input 的文本内容
    command: str = ""                  # /slash 命令
    args: str = ""                     # 命令参数
    session_id: str = ""               # resume_session 的 session ID

@dataclass
class ServerEvent:
    type: str                          # thinking_delta | text_delta | tool_call | tool_result | stream_end | command_result | status | error | server_event
    # ... 各字段按需
```

---

## 四、Server 详细设计

### 4.1 目录结构

```
server/
├── __init__.py
├── app.py                # BrixServerApp — 核心应用逻辑
├── transport.py          # WebSocket 传输层 (Unix Socket + TCP)
├── session_handler.py    # 多 Session 管理 (per-connection MemoryProvider)
├── types.py              # 协议消息类型
├── daemon.py             # 守护进程管理 (PID file, 信号, fork)
└── api/
    ├── __init__.py
    ├── chat.py           # handle_chat() — 流式聊天处理
    ├── commands.py       # handle_command() — /slash 命令路由
    └── sessions.py       # 会话 CRUD
```

### 4.2 BrixServerApp 核心类

```python
class BrixServerApp:
    """无头核心 — 等价于去掉所有 UI + voice 的 BrixCLI。

    Server 只保留逻辑，不拥有任何 IO 设备或 UI 组件。
    """

    def __init__(self, config: dict):
        # === 与当前 BrixCLI 相同的核心组件 ===
        self._data_dir = config.get("memory", {}).get("data_dir", "memory/data")
        self._llm_client = LLMClient(config)
        self._tool_runner = ToolRunner()
        self._command_registry = CommandRegistry()
        self._side_manager = SideTaskManager()
        self._side_manager.configure(config=config, llm_client=self._llm_client, memory=None)
        self._register_tools()
        self._register_commands()
        self._register_skill_tool()
        for task in ALL_TASKS:
            self._side_manager.register(task)
        self._orchestrator = self._build_orchestrator(config)
        self._config = config
        # === 新增：多 session 管理 ===
        self._session_contexts: dict[str, SessionContext] = {}

    async def handle_chat(self, content: str, ctx: SessionContext) -> AsyncGenerator[ServerEvent, None]:
        """处理一条聊天消息，yield 流式事件序列。

        核心逻辑从 BrixCLI._process_streaming() 迁移而来，
        去掉所有 Rich Console / StreamRenderer / ToolDisplay 调用。
        """
        ...

    async def handle_command(self, command: str, args: str, ctx: SessionContext) -> ServerEvent:
        """执行 slash 命令，返回结构化结果。

        与 BrixCLI._handle_command() 等价，但：
        - 不调用 print() / sys.exit()
        - 不调用 console.print()
        - 返回 CommandResult → 序列化为 ServerEvent
        """
        ...

    def create_session_context(self, client_id: str) -> SessionContext:
        """为新连接创建独立的 SessionContext（含独立 MemoryProvider）"""
        ...

    def release_session_context(self, client_id: str) -> None:
        """客户端断开时释放 session 资源（保存 session，清理 reference）"""
        ...

    async def shutdown(self) -> None:
        """优雅关闭：保存所有 session、关闭 LLM client、清理 side tasks"""
        ...
```

### 4.3 多 Session 并发模型

每个 WebSocket 连接拥有独立的 `SessionContext`：

```python
@dataclass
class SessionContext:
    client_id: str                     # WebSocket 连接标识
    memory: MemoryProvider             # 独立的 MemoryProvider 实例
    current_session_id: str | None     # 当前活跃的 session UUID
```

- 多个 SessionContext 共享同一个 `data_dir`（文件系统层）
- fcntl 文件锁（`memory/session.py` 已有）保护同一 session 文件的并发写入
- 不同 session 文件之间无冲突
- 读操作（list_sessions、load_session）天然并发安全

### 4.4 Server 生命周期

```
启动 (brix serve)
  │
  ├─→ fork 到后台（除非 --foreground）
  ├─→ 写 PID 文件 (~/.brix/server.pid)
  ├─→ 初始化 BrixServerApp（内存、LLM、tools、commands）
  ├─→ 启动 SideTaskManager
  ├─→ 监听 Unix Socket (~/.brix/server.sock)
  ├─→ [可选] 监听 TCP 端口
  ├─→ [可选] 启动 macOS 状态栏 App
  └─→ 输出 "Server started. PID: 12345"

运行中
  ├─→ 接受 WebSocket 连接
  ├─→ 为每个连接创建 SessionContext
  ├─→ 处理 chat / command / session 请求
  └─→ 处理 SIGTERM → 触发 graceful shutdown

关闭 (brix stop / SIGTERM)
  ├─→ 广播 "shutting_down" 事件给所有客户端
  ├─→ 保存所有活跃 session
  ├─→ 关闭 LLM client HTTP sessions
  ├─→ 停止 SideTaskManager
  ├─→ 清理 Unix Socket 文件
  ├─→ 清理 PID 文件
  └─→ 退出进程
```

### 4.5 关键设计决策

| 决策 | 理由 |
|------|------|
| **Voice 模块完全留在 Client** | 音频硬件（麦克风/扬声器）是客户端 OS 独有的；Server 不应触碰设备。Client 完成 STT 后通过 `voice_input` 消息将文本发给 Server |
| **每个连接独立 MemoryProvider** | 不同客户端可能操作不同 session；MemoryProvider 内部有 `_current_session_id` 状态，是 per-connection 的 |
| **Server 关闭前端不关闭** | Server 是常驻进程；TUI / 状态栏 App 关闭只是断开 WebSocket 连接，Server 继续运行 |
| **fcntl 保护并发写** | 现有 `memory/session.py` 已有文件锁；多个 session 上下文写不同文件无冲突 |
| **本地模型在 Server 加载** | 所有客户端共享同一份模型内存，避免重复加载 |

---

## 五、Client 架构

### 5.1 TUI Client（改造后）

```python
# cli/app.py — 改造为 BrixTUIClient

class BrixTUIClient:
    """TUI 客户端 — 只负责渲染和输入，不拥有任何核心逻辑。

    对比当前 BrixCLI (~847 行)：
    - 删除：_memory, _llm_client, _tool_runner, _orchestrator, _command_registry, _side_manager
    - 删除：_register_tools(), _register_commands(), _build_orchestrator(), _build_dynamic_context()
    - 删除：_process(), _process_streaming() 中的所有 orchestrator/LLM 调用
    - 保留：所有 UI 渲染器 (StreamRenderer, ThinkingRenderer, ToolDisplay, StatusBar, StageIndicator)
    - 保留：PromptSession, Banner, Completer, Console
    - 新增：BrixTransport (WebSocket client), server 自动检测与启动
    """

    def __init__(self):
        self._transport: BrixTransport | None = None
        self._console = Console(theme=BRIX_THEME)
        self._voice: VoiceRuntimeImpl | None = None  # 语音硬件在客户端
        self._init_voice()  # 不变

    async def _ensure_server(self) -> None:
        """确保 server 正在运行。未运行时自动后台启动。"""

    async def _connect(self) -> None:
        """通过 Unix Socket 连接 server，建立 WebSocket。"""

    async def run(self) -> None:
        """REPL 主循环。"""
        await self._ensure_server()
        await self._connect()
        # 渲染 Banner ...
        while True:
            text = await self._read_input()  # keyboard 或 voice
            if text.startswith("/"):
                await self._handle_command(text)
            else:
                await self._send_chat_and_render(text)

    async def _send_chat_and_render(self, content: str) -> None:
        """发送 chat 消息，接收流式事件并用 UI 渲染器渲染。"""
        renderer = None
        thinking_renderer = None
        async for event in self._transport.send_chat(content):
            if event.type == "thinking_delta":
                # 启动 ThinkingRenderer...
            elif event.type == "text_delta":
                # 切换到 StreamRenderer...
            elif event.type == "tool_call":
                # 调用 ToolDisplay.show_tool_start()...
            elif event.type == "tool_result":
                # 调用 ToolDisplay.show_tool_result()...
            elif event.type == "stream_end":
                break
```

### 5.2 BrixTransport — WebSocket 客户端封装

```python
# client/transport.py

class BrixTransport:
    """统一的 WebSocket 客户端，封装连接、发送、接收。

    使用方式:
        transport = BrixTransport.local()     # Unix Socket
        transport = BrixTransport.remote("192.168.1.100", 8080)  # TCP
    """

    @classmethod
    def local(cls, socket_path: str = "~/.brix/server.sock") -> "BrixTransport": ...

    @classmethod
    def remote(cls, host: str, port: int, ssl: bool = False) -> "BrixTransport": ...

    async def connect(self) -> None: ...

    async def send_chat(self, content: str) -> AsyncGenerator[ServerEvent, None]:
        """发送 chat 消息，返回 server 事件的 async generator。"""
        ...

    async def send_command(self, command: str, args: str = "") -> ServerEvent: ...

    async def send_voice_input(self, content: str) -> AsyncGenerator[ServerEvent, None]: ...

    async def send_session_management(self, action: str, **kwargs) -> ServerEvent: ...

    async def get_status(self) -> ServerEvent: ...

    async def close(self) -> None: ...
```

### 5.3 语音归属

```
┌─ TUI Client ─────────────────────────────────────┐
│                                                    │
│  麦克风 → VAD → STT                                  │
│              │                                      │
│              ↓ (文本 "今天天气怎么样")                  │
│     ws.send({"type": "voice_input",                 │
│              "content": "今天天气怎么样"})             │
│              │                                      │
│              ↓ WebSocket                            │
│         ┌────┴─────┐                                │
│         │  Server  │  ← 处理，返回文本回复              │
│         └────┬─────┘                                │
│              ↓                                      │
│  扬声器 ← TTS ← 文本回复                              │
│                                                    │
└────────────────────────────────────────────────────┘
```

- STT 在客户端执行（本地 faster-whisper 或在线 Qwen-ASR）
- TTS 在客户端执行（CosyVoice API 调用 + 音频播放）
- Server 只看到文本，不接触任何音频流

---

## 六、CLI 命令设计（用户视角）

### 6.1 核心命令（最常用）

```bash
# 启动无头 server（不会打开 TUI）
brix serve

# 输出:
#   Brix Server v0.2.0
#   ✓ Server started. PID: 12345
#   ✓ Listening: unix://~/.brix/server.sock
#   Model: zenmux-openai/deepseek/deepseek-v4-flash
```

```bash
# 一键启动 server + TUI（最常用）
brix

# 输出:
#   (检测到 server 未运行 → 自动后台启动 → 等待就绪)
#   ✓ Server ready
#
#   ██████╗ ██████╗ ██╗██╗  ██╗
#   ██╔══██╗██╔══██╗██║╚██╗██╔╝
#   ██████╔╝██████╔╝██║ ╚███╔╝
#   ██╔══██╗██╔══██╗██║ ██╔██╗
#   ██████╔╝██║  ██║██║██╔╝ ██╗
#   ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝
#     BRIX — Personal AI Agent
#
#   ❯ _
```

### 6.2 Server 管理命令

```bash
# 查看 server 状态
brix status
# 输出:
#   Server:  ● running  (PID: 12345, uptime: 2h 15m)
#   Model:   zenmux-openai/deepseek/deepseek-v4-flash
#   Sessions: 3 active (1024 total)
#   Local:   unix://~/.brix/server.sock
#   Remote:  disabled

# 停止 server（所有前端将断开连接）
brix stop
# 输出:
#   ✓ Server stopped. 3 sessions saved.

# 前台运行 server（调试用，Ctrl+C 停止）
brix serve --foreground
```

### 6.3 远程访问（可选）

```bash
# 启动 server 并开放远程端口
brix serve --port 8080
# 输出:
#   ✓ Server started. PID: 12345
#   ✓ Local:  unix://~/.brix/server.sock
#   ✓ Remote: ws://0.0.0.0:8080
#   ⚠  Remote access enabled — use with caution on public networks

# TUI 连接远程 server
brix --remote 192.168.1.100:8080
```

### 6.4 自动化逻辑

```
用户输入 brix
  │
  ├─→ 尝试连接 ~/.brix/server.sock
  │     ├─ 成功 → 直接启动 TUI，连接 server
  │     └─ 失败 ↓
  │
  ├─→ 检查 ~/.brix/server.pid 是否有残留进程
  │     ├─ 是 → 尝试 SIGTERM → 等待 → SIGKILL → 清理 PID+socket
  │     └─ 否 → 继续
  │
  ├─→ 后台启动 server: brix serve (fork)
  ├─→ 轮询 ~/.brix/server.sock（最多等待 5 秒）
  │     ├─ 就绪 → 启动 TUI，连接 server
  │     └─ 超时 → 报错退出
  │
  └─→ [Phase 2+] 检测 macOS 状态栏 App 是否存在
        ├─ 存在且未运行 → 启动状态栏 App
        └─ 不存在/已运行 → 跳过
```

### 6.5 关键行为规则

| 行为 | 规则 |
|------|------|
| 关闭 TUI (Ctrl+C 或 /quit) | 断开 WebSocket，**Server 继续运行** |
| 关闭 macOS 状态栏 App | 断开 WebSocket，**Server 继续运行** |
| 关闭 macOS 完整 GUI App | 断开 WebSocket，**Server 继续运行** |
| 执行 `brix stop` | **Server 保存所有 session 后退出** |
| 系统关机 | SIGTERM → Server 优雅关闭 |
| Server 崩溃 | 客户端检测到连接断开 → 显示 "Connection lost" → 可 `brix serve` 重启 |

---

## 七、分阶段实施计划

### Phase 1: 架构分离 + TUI 适配

**目标**: `brix serve` 可独立启动无头 Server；`brix` 一键启动 Server+TUI。TUI 完全通过 WebSocket 与 Server 通信。

#### 1.1 创建协议层 (`protocol/`)

- `protocol/types.py`: 定义 `ClientMessage`、`ServerEvent` dataclass 及 JSON 序列化
- `protocol/transport.py`: `BrixTransport` 基类，封装 WebSocket 连接/收发
- **产出物**: `protocol/` 目录，含类型定义和 transport 抽象

#### 1.2 创建 Server (`server/`)

- `server/app.py`: `BrixServerApp` 核心类
  - 从 `BrixCLI` 迁移：`_register_tools()`、`_register_commands()`、`_register_skill_tool()`、`_build_orchestrator()`、`_build_dynamic_context()`、SideTaskManager 初始化
  - 新增：`handle_chat()`（从 `_process_streaming()` 去掉 UI 渲染）、`handle_command()`（从 `_handle_command()` 去掉 UI 副作用）、`create_session_context()`、`release_session_context()`
- `server/session_handler.py`: `SessionContext` 管理和并发
- `server/transport.py`: Unix Socket WebSocket server + 可选的 TCP
- `server/daemon.py`: 进程守护（fork、PID file、信号处理）
- `server/api/`: chat、commands、sessions 处理逻辑
- **产出物**: `server/` 包，可独立运行

#### 1.3 改造 CLI 入口 (`main.py`)

- 子命令路由：
  - `brix serve [--foreground] [--port PORT]` → 启动 Server
  - `brix [--remote HOST:PORT]` → 自动检测/启动 Server + 启动 TUI
  - `brix stop` → 发送 SIGTERM 给 Server
  - `brix status` → 查询 Server 状态（PID、端口、运行时间）
- `brix serve` 逻辑：
  1. 检查是否已有 Server 运行（PID 文件 + 进程存活检测）
  2. 未运行则 fork 到后台，写 PID 文件
  3. 初始化 BrixServerApp，启动 WebSocket 监听
  4. 输出一行成功信息
- `brix` (TUI 启动) 逻辑：
  1. 尝试连接 Unix Socket
  2. 连接失败 → 自动启动 Server（同 `brix serve`），等待就绪
  3. 连接成功 → 启动 TUI Client
- **产出物**: `main.py` 重写，支持子命令路由

#### 1.4 改造 TUI 为瘦客户端 (`cli/app.py`)

- 删除所有核心组件引用（`_memory`、`_llm_client`、`_tool_runner`、`_orchestrator`、`_command_registry`、`_side_manager`）
- 删除 `_register_tools()`、`_register_commands()`、`_register_skill_tool()`、`_build_orchestrator()`、`_build_dynamic_context()`、`_process()`、`_process_streaming()`
- 新增 `_transport: BrixTransport`，通过 WebSocket 通信
- `_send_chat_and_render()`: ws.send(chat) → 接收 ServerEvent stream → 调用 UI 渲染器
- `_handle_command()`: ws.send(command) → 接收 command_result → 客户端处理副作用
  - `/quit` → 不 `sys.exit(0)`，改为发送 command 给 server，断开连接，优雅退出 REPL
  - `/resume` → server 返回 session 数据，客户端用 PaginatedSelector 渲染
- Voice 保留在客户端不变，新增 voice 文本桥接（`voice_input` 消息发给 server）
- **产出物**: 重写 `cli/app.py`，BrixTUIClient 约 400-500 行

#### 1.5 验证点

- [ ] `brix serve` 启动后，Server 进程独立存在，不在终端显示任何交互 UI
- [ ] `brix` 在 Server 未运行时自动启动 Server，然后打开 TUI
- [ ] `brix` 在 Server 已运行时直接打开 TUI，连接已有 Server
- [ ] 在 TUI 中正常对话（chat、tool calls、thinking 渲染均正常）
- [ ] 在 TUI 中使用 `/resume`、`/clear`、`/model`、`/help` 等命令正常
- [ ] 关闭 TUI（Ctrl+C）后，Server 继续运行（`brix status` 显示 running）
- [ ] `brix stop` 优雅关闭 Server
- [ ] 所有现有测试通过（必要时更新测试以适配新架构）

---

### Phase 2: macOS 状态栏 App

**目标**: 开发原生 macOS 菜单栏应用，显示 Server 状态，提供快捷控制。当 Server 启动时自动打开。

#### 2.1 功能规格

| 功能 | 描述 |
|------|------|
| 菜单栏图标 | 绿色圆点 = Server 运行中；灰色圆点 = 未连接 |
| 状态显示 | 下拉显示：当前模型、活跃 session 数、Server 运行时间 |
| 快捷操作 | Open TUI（在新终端窗口打开 `brix`）、Stop Server |
| 自动启动 | 当 `brix serve` 或 `brix` 启动 Server 后，自动检测并打开状态栏 App |
| 自动关闭 | 检测到 Server 断开连接后，App 自动退出 |

#### 2.2 技术选型

- **语言**: Swift + SwiftUI (AppKit NSStatusBar)
- **通信**: 通过 Unix Socket WebSocket 连接 Server（使用 `URLSessionWebSocketTask` 或第三方 WebSocket 库如 Starscream）
- **进程管理**: 通过 `NSWorkspace` 检测 Server 进程状态
- **打包**: 独立的 `.app` bundle，放置在 Brix 项目目录或 `/Applications`

#### 2.3 与 CLI 的集成

```bash
# brix serve 启动时
brix serve
# 内部逻辑:
#   1. fork server 进程
#   2. 检测 macOS 状态栏 App 是否存在 (~/Applications/Brix/BrixStatusBar.app)
#      - 存在且未运行 → open BrixStatusBar.app
#      - 不存在 → 跳过（静默，无报错）
#   3. 输出 "✓ Server started. PID: 12345"

# brix 启动 TUI 时同理
brix
# 内部逻辑:
#   1. 确保 server 运行
#   2. 同上检测并打开状态栏 App
#   3. 启动 TUI
```

#### 2.4 UI 示意

```
菜单栏: [●]

点击展开:
┌─────────────────────────────┐
│ Brix                        │
│ ● Server Running            │
│                             │
│ Model: deepseek-v4-flash    │
│ Sessions: 3 active          │
│ Uptime: 2h 15m              │
├─────────────────────────────┤
│ Open TUI                    │
│ Stop Server                 │
├─────────────────────────────┤
│ Quit Status Bar             │
└─────────────────────────────┘
```

#### 2.5 验证点

- [ ] Server 启动后，状态栏自动出现绿色圆点图标
- [ ] 下拉菜单显示正确的模型名、session 数、运行时间
- [ ] "Open TUI" 在新终端窗口启动 `brix` 命令
- [ ] "Stop Server" 发送停止信号，Server 正常退出
- [ ] 关闭状态栏 App 不影响 Server 运行
- [ ] Server 被手动停止（`brix stop`）后，状态栏图标变灰，App 可自动退出

---

### Phase 3: macOS 完整 GUI App

**目标**: 开发原生 macOS 桌面应用，替代 TUI 提供更好的图形交互体验。

#### 3.1 功能规格

| 功能 | 描述 |
|------|------|
| 聊天界面 | 对话气泡、Markdown 渲染、代码块高亮、流式输出动画 |
| 会话管理 | 侧边栏显示历史会话列表、创建/切换/删除会话 |
| 工具调用展示 | 可折叠的工具调用面板，显示参数和结果 |
| Thinking 展示 | 可折叠的推理过程面板 |
| 模型切换 | 下拉菜单选择模型 |
| 语音交互 | 内建麦克风采集 + TTS 播放（系统权限管理） |
| 文件拖放 | 支持拖放文件到聊天框 |
| 系统集成 | 通知、Dock 图标、快捷键 |

#### 3.2 技术选型

- **语言**: Swift + SwiftUI
- **通信**: Unix Socket WebSocket（同 TUI）
- **Markdown 渲染**: 使用 `AttributedString` + 自定义渲染器
- **代码高亮**: 使用 `Highlightr` 或 `Splash`

#### 3.3 与 Server 的关系

- 完全通过 WebSocket JSON 协议通信
- 不需要 Server 做任何改动
- 不需要任何 Server 端代码了解 GUI 的存在

---

### Phase 4: Mobile App

**目标**: 开发 iOS / Android 移动端应用，支持远程连接 Server。

#### 4.1 功能规格

| 功能 | 描述 |
|------|------|
| 聊天界面 | 移动端适配的对话气泡、Markdown 渲染 |
| 远程连接 | 输入 Server 地址+端口（或扫码连接） |
| 语音交互 | 移动端原生 STT + TTS |
| 会话同步 | 与桌面端共享同一套 session 数据 |
| 通知 | 后台保持连接（可选），推送通知 |

#### 4.2 技术选型

- **框架**: Flutter（跨平台）或 SwiftUI + Jetpack Compose（原生）
- **通信**: TCP WebSocket（可升级为 WSS + Token 认证）
- **安全**: TLS + Bearer Token 认证

#### 4.3 与 Server 的关系

- 通过 TCP WebSocket JSON 协议通信，与本地客户端使用完全相同的消息格式
- Server 端只需启动时开启 `--port` 选项
- 不需要 Server 做任何协议层改动

---

## 八、Server 数据流详解

### 8.1 Chat 流：端到端

```
Client (TUI/macOS)                          Server
─────────────────                           ──────

用户输入: "帮我写排序"
  │
  ├─→ ws.send({type:"chat", content:"帮我写排序"})
  │                                         │
  │                                    ┌────┴────┐
  │                                    │ 创建/获取 │
  │                                    │ SessionCtx│
  │                                    └────┬────┘
  │                                         │
  │                                    ┌────┴────┐
  │                                    │ build    │
  │                                    │ system   │
  │                                    │ prompt   │
  │                                    └────┬────┘
  │                                         │
  │                                    ┌────┴────┐
  │                                    │ Side:    │
  │                                    │ history  │
  │                                    │ search   │
  │                                    └────┬────┘
  │                                         │
  │                                    ┌────┴────┐
  │                                    │ Orchestr │
  │                                    │ ator.run │
  │                                    │ _stream  │
  │                                    └────┬────┘
  │                                         │
  │  ← {type:"thinking_delta", text:"..."}  │
  │  ← {type:"text_delta", text:"这是"}      │
  │  ← {type:"text_delta", text:"快速排序"}  │
  │  ← {type:"tool_call", name:"read_file"} │
  │  ← {type:"tool_result", result:"..."}   │
  │  ← {type:"text_delta", text:"..."}      │
  │  ← {type:"stream_end"}                  │
  │                                         │
  ├─→ 渲染完成                                │
  │                                         │
  │                                    ┌────┴────┐
  │                                    │ persist │
  │                                    │ session │
  │                                    └────┬────┘
  │                                         │
  │                                    ┌────┴────┐
  │                                    │ Side:    │
  │                                    │ title/   │
  │                                    │ summary  │
  │                                    │ (fire&   │
  │                                    │ forget)  │
  │                                    └─────────┘
```

### 8.2 Slash Command 流

```
Client                                      Server
──────                                      ──────

用户输入: /resume
  │
  ├─→ ws.send({type:"command", command:"/resume"})
  │                                         │
  │                                    ┌────┴────┐
  │                                    │ command  │
  │                                    │ registry │
  │                                    └────┬────┘
  │                                         │
  │  ← {type:"command_result",              │
  │      command:"/resume",                 │
  │      data:{sessions:[...]}}             │
  │                                         │
  ├─→ Client 用 PaginatedSelector 渲染列表    │
  │                                         │
  ├─→ ws.send({type:"resume_session",       │
  │            session_id:"abc..."})         │
  │                                         │
  │  ← {type:"command_result",              │
  │      data:{resumed_session_id:"abc...",  │
  │            messages:[...]}}             │
  │                                         │
  ├─→ Client 用 render_history() 渲染历史     │
```

---

## 九、配置变更

### 9.1 新增 Server 配置 (`config/settings.yaml`)

```yaml
# ============================================================
# Server 配置
# ============================================================
server:
  # Unix socket 路径
  socket_path: "~/.brix/server.sock"

  # 远程访问（默认禁用）
  remote:
    enabled: false
    host: "0.0.0.0"
    port: 8080
    # 未来扩展: TLS cert, auth token

  # PID 文件路径
  pid_file: "~/.brix/server.pid"

  # 本地模型配置（未来）
  local_models:
    enabled: false
    models_dir: "~/.brix/models"
    runtime: "ollama"               # ollama | llama.cpp | mlx
```

### 9.2 不变配置

- `providers`、`models`、`routing`、`retry` — 完全不变
- `memory` — 完全不变（路径、token 限制等）
- `side` — 完全不变
- `voice` — 移到客户端配置（每个客户端独立配置自己的音频设备）
- `engine` — 完全不变
- `status_bar` — 属于 TUI 客户端配置

---

## 十、项目目录变更

```
Brix/
├── main.py                      # 重写: 子命令路由 (serve / client / stop / status)
├── cli/
│   ├── app.py                   # 重写: BrixTUIClient (瘦客户端 ~400-500行)
│   ├── transport.py             # 新增: BrixTransport (WebSocket 客户端)
│   └── ...                      # 其他 CLI 组件不变
├── server/                      # 新增: 无头 Server
│   ├── __init__.py
│   ├── app.py                   # BrixServerApp
│   ├── transport.py             # WebSocket Server (Unix + TCP)
│   ├── session_handler.py       # 多 Session 管理
│   ├── daemon.py                # PID/信号/fork 管理
│   └── api/
│       ├── __init__.py
│       ├── chat.py
│       ├── commands.py
│       └── sessions.py
├── protocol/                    # 新增: 共享协议类型
│   ├── __init__.py
│   ├── types.py                 # ClientMessage, ServerEvent
│   └── transport.py             # BrixTransport 基类
├── memory/                      # 不变 (已经是 Protocol 化)
├── orchestrator/                # 不变 (已经是 Protocol 化)
├── capability/                  # 不变 (Tool/ToolRunner 不变)
│   └── voice/                   # 保留在客户端
├── infra/                       # 不变
├── side/                        # 不变
├── hooks/                       # 不变
├── log/                         # 不变 (FlowLog 写入移到 server 端)
├── config/                      # 新增 server 配置段
├── plugins/                     # 不变
├── tests/                       # 更新以适配新架构
└── macOS/                       # Phase 2+ 新增
    ├── BrixStatusBar/           # macOS 状态栏 App (Swift)
    └── BrixApp/                 # macOS 完整 GUI App (Swift) — Phase 3
```

---

## 十一、风险与注意事项

| 风险 | 缓解措施 |
|------|---------|
| **Phase 1 工作量大** (涉及 4 个层面) | 严格按 1.1→1.2→1.3→1.4 顺序推进，每步可独立验证 |
| **BrixCLI 中 UI 和逻辑深度耦合** | `run_stream()` 已经通过 yield event 分离，这是关键优势；`_process_streaming()` 中的渲染逻辑有明确的边界 |
| **slash 命令有 UI 副作用** | `/resume` 的 PaginatedSelector 在 client 端；`/quit` 改为 client 端断开连接而非 sys.exit |
| **fcntl 文件锁在 NFS 上不可靠** | 本项目是单机部署，不涉及 NFS |
| **Server 崩溃导致数据丢失** | 现有 `memory/storage.py` 已有原子写入（temp file + rename），崩溃不会损坏数据 |
| **多个 Client 同时操作同一 session** | 设计上允许；fcntl 保护写入；但语义上需考虑是否限制（可后续加入 session 级别的排他锁） |

---

## 十二、Phase 1 后验收清单

- [ ] `brix serve` 启动后，Server 作为独立后台进程运行，不在当前终端显示交互 UI
- [ ] `brix serve --foreground` 前台运行，Ctrl+C 优雅退出
- [ ] `brix`（Server 未运行时）自动启动 Server + 打开 TUI
- [ ] `brix`（Server 已运行时）直接打开 TUI，不重复启动 Server
- [ ] TUI 中正常对话（thinking 折叠、流式文本、tool call 面板）
- [ ] TUI 中所有 slash 命令正常工作
- [ ] 语音输入 → Client STT → `voice_input` 消息 → Server 处理 → 回复 → Client TTS 正常工作
- [ ] 关闭 TUI（Ctrl+C）后 Server 继续运行（`brix status` 确认）
- [ ] 关闭 TUI 后重新 `brix` 可正常连接已有 Server
- [ ] `brix stop` 优雅关闭 Server（所有 session 被保存）
- [ ] 多个 TUI 实例可同时连接 Server，各自独立 session
- [ ] 所有现有测试通过
