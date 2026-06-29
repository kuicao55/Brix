# Phase 1 实施计划：架构分离 + TUI 适配

> 版本: 1.0  
> 日期: 2026-06-28  
> 状态: 待审批

---

## 一、总体目标

将 Brix 从单体 TUI 进程拆分为 **Server + Client** 架构：

- `brix serve` — 启动无头 Server（后台进程）
- `brix` — 自动检测/启动 Server + 打开 TUI
- `brix stop` — 优雅关闭 Server
- `brix status` — 查询 Server 状态

**技术选型**：
- WebSocket 库：`websockets`（纯 Python，asyncio 原生，支持 Unix Socket）
- Server 启动方式：`subprocess`（避免 fork 的 asyncio 陷阱）
- 本地通信：Unix Domain Socket（`~/.brix/server.sock`）
- 远程通信：TCP WebSocket（可选，Phase 1 可选实现）

---

## 二、任务拆解与依赖关系

```
┌─────────────────────────────────────────────────────────────────┐
│                    Phase 1 任务依赖图                            │
└─────────────────────────────────────────────────────────────────┘

    [1.1 协议层]  ─────────────────────────────┐
         │                                      │
         ▼                                      ▼
    [1.2 Server 核心]  ◄────────────────  [1.3 CLI 入口]
         │                                      │
         ▼                                      ▼
    [1.4 TUI 瘦身]  ──────────────────────► [1.5 集成测试]
```

**推荐执行顺序**：1.1 → 1.2 → 1.3 → 1.4 → 1.5

每个阶段可独立验证，确保进度可控。

---

## 三、详细任务拆解

### 3.1 阶段 1：创建协议层 (`protocol/`)

**目标**：定义 Server-Client 通信的消息类型和传输抽象

#### 任务 1.1.1：创建 `protocol/types.py`

**文件**：`protocol/types.py`（新建）

**内容**：
```python
@dataclass
class ClientMessage:
    """Client → Server 消息"""
    type: str  # chat | command | list_sessions | resume_session | create_session | get_status | voice_input
    content: str = ""
    command: str = ""
    args: str = ""
    session_id: str = ""

@dataclass
class ServerEvent:
    """Server → Client 事件"""
    type: str  # thinking_delta | text_delta | tool_call | tool_result | stream_end | command_result | status | error | server_event
    # 各字段按需添加
```

**验证方式**：
- [ ] 单元测试：创建 `ClientMessage` 和 `ServerEvent` 实例，验证 JSON 序列化/反序列化
- [ ] 验证所有消息类型都有对应的 dataclass 定义

#### 任务 1.1.2：创建 `protocol/transport.py`

**文件**：`protocol/transport.py`（新建）

**内容**：
```python
class BrixTransport:
    """WebSocket 客户端封装"""
    
    @classmethod
    def local(cls, socket_path: str = "~/.brix/server.sock") -> "BrixTransport": ...
    
    @classmethod
    def remote(cls, host: str, port: int, ssl: bool = False) -> "BrixTransport": ...
    
    async def connect(self) -> None: ...
    async def send_chat(self, content: str) -> AsyncGenerator[ServerEvent, None]: ...
    async def send_command(self, command: str, args: str = "") -> ServerEvent: ...
    async def close(self) -> None: ...
```

**验证方式**：
- [ ] 单元测试：mock websockets，验证 `send_chat` 返回正确的事件流
- [ ] 验证 `local()` 和 `remote()` 工厂方法

#### 任务 1.1.3：创建 `protocol/__init__.py`

**文件**：`protocol/__init__.py`（新建）

**内容**：导出 `ClientMessage`、`ServerEvent`、`BrixTransport`

**验证方式**：
- [ ] 导入测试：`from protocol import ClientMessage, ServerEvent, BrixTransport`

---

### 3.2 阶段 2：创建 Server (`server/`)

**目标**：实现无头 Server，包含核心逻辑、WebSocket 传输、Session 管理

#### 任务 1.2.1：创建 `server/app.py` — BrixServerApp 核心类

**文件**：`server/app.py`（新建）

**内容**：
```python
class BrixServerApp:
    """无头核心 — 等价于去掉所有 UI + voice 的 BrixCLI"""
    
    def __init__(self, config: dict):
        # 从 BrixCLI 迁移的核心组件初始化
        self._llm_client = LLMClient(config)
        self._tool_runner = ToolRunner()
        self._command_registry = CommandRegistry()
        self._side_manager = SideTaskManager()
        self._orchestrator = self._build_orchestrator(config)
        self._session_contexts: dict[str, SessionContext] = {}
        
        # 注册工具、命令、Skill
        self._register_tools()
        self._register_commands()
        self._register_skill_tool()
    
    async def handle_chat(self, content: str, ctx: SessionContext) -> AsyncGenerator[ServerEvent, None]:
        """处理聊天消息，yield 流式事件"""
        # 从 BrixCLI._process_streaming() 迁移，去掉所有 UI 渲染
        
        # 关键：SideTaskManager 的 memory 不绑定到实例级，
        # 而是在每次调用时通过 SessionContext 传入
        # session_messages 来自 ctx.memory.get_context_messages()，
        # 而非全局 memory
        ...
    
    async def handle_command(self, command: str, args: str, ctx: SessionContext) -> ServerEvent:
        """执行 slash 命令"""
        # 从 BrixCLI._handle_command() 迁移，去掉 print/sys.exit
        ...
    
    def create_session_context(self, client_id: str) -> SessionContext:
        """为新连接创建独立的 SessionContext"""
        ...
    
    async def shutdown(self) -> None:
        """优雅关闭"""
        ...
```

**迁移来源**：
- `cli/app.py` 的 `__init__()` 中的核心组件初始化（第 64-108 行）
- `cli/app.py` 的 `_register_tools()`（第 637-656 行）→ 需要改造 memory 依赖
- `cli/app.py` 的 `_register_commands()`（第 775-809 行）
- `cli/app.py` 的 `_register_skill_tool()`（第 811-819 行）
- `cli/app.py` 的 `_build_orchestrator()`（第 821-830 行）
- `cli/app.py` 的 `_process_streaming()`（第 380-632 行）→ 去掉 UI 渲染
- `cli/app.py` 的 `_handle_command()`（第 262-301 行）→ 去掉 print/sys.exit

**关键修正**：
1. **SideTaskManager 与 per-connection memory**：SideTaskManager 是全局共享的，但 `run_task()` / `fire_and_forget()` 传入的 `session_messages` 应来自当前 `SessionContext.memory`，而非全局 memory。需要检查每个 side task（尤其是 `session_summary`、`session_title`）是否会错误地访问全局 memory 状态。

2. **`_register_tools()` 中的 memory 依赖**：`MemorySearchTool` 和 `SaveMemoryTool` 需要改造，使其能根据当前连接找到正确的 `MemoryProvider`。方案 A（推荐）：工具参数中传入 `client_id`，`ToolRunner` 在 execute 时根据 `client_id` 查找 `SessionContext` → 获取 memory。

**验证方式**：
- [ ] 单元测试：创建 `BrixServerApp` 实例，验证组件初始化
- [ ] 集成测试：mock LLM，验证 `handle_chat()` 返回正确的事件流
- [ ] 验证 `handle_command()` 返回结构化结果而非直接打印
- [ ] 验证多个连接的 session 完全独立（memory、side task 互不干扰）

#### 任务 1.2.2：改造 MemorySearchTool 和 SaveMemoryTool — per-connection memory

**文件**：`capability/tools/memory_search.py`（修改）、`capability/tools/save_memory.py`（修改）

**问题**：
当前 `MemorySearchTool` 和 `SaveMemoryTool` 绑定了固定的 `MemoryProvider` 实例。在 server 端，不同连接的 search/save 应作用于各自 session 的 memory。

**方案 A（推荐）**：工具参数中传入 `client_id`，`ToolRunner` 在 execute 时根据 `client_id` 查找 `SessionContext` → 获取 memory。

**改动**：
1. `MemorySearchTool` 和 `SaveMemoryTool` 的 `execute()` 方法新增 `client_id` 参数
2. `BrixServerApp` 维护 `client_id → SessionContext` 的映射
3. 工具执行时，根据 `client_id` 获取当前连接的 `MemoryProvider`

```python
# capability/tools/memory_search.py
class MemorySearchTool(Tool):
    def __init__(self, server_app: "BrixServerApp"):
        self._server_app = server_app
    
    async def execute(self, query: str, client_id: str = "", **kwargs) -> str:
        # 根据 client_id 获取当前连接的 memory
        ctx = self._server_app.get_session_context(client_id)
        if not ctx:
            return "Error: No active session"
        searcher = ctx.memory.searcher
        if not searcher:
            return "Error: Memory search not available"
        # 执行搜索
        ...

# capability/tools/save_memory.py
class SaveMemoryTool(Tool):
    def __init__(self, server_app: "BrixServerApp"):
        self._server_app = server_app
    
    async def execute(self, content: str, client_id: str = "", **kwargs) -> str:
        # 根据 client_id 获取当前连接的 memory
        ctx = self._server_app.get_session_context(client_id)
        if not ctx:
            return "Error: No active session"
        short_term = ctx.memory.short_term
        if not short_term:
            return "Error: Short-term memory not available"
        # 保存记忆
        ...
```

**影响范围**：
- `BashTool`、`FileReadTool`、`FileWriteTool`、`FileEditTool`、`CalculatorTool`、`WeatherTool` 不涉及 session 状态，不受影响
- `SkillTool` 可能需要类似改造（取决于是否访问 memory）

**验证方式**：
- [ ] 单元测试：验证 `MemorySearchTool` 和 `SaveMemoryTool` 能正确根据 `client_id` 获取 memory
- [ ] 集成测试：两个连接各自 search/save，验证互不干扰
- [ ] 验证其他工具（BashTool 等）不受影响

---

#### 任务 1.2.3：创建 `server/session_handler.py` — Session 管理

**文件**：`server/session_handler.py`（新建）

**关键修正**：`SessionHandler` 需要维护 `client_id → SessionContext` 的映射，供 `MemorySearchTool` 和 `SaveMemoryTool` 查询。

**内容**：
```python
@dataclass
class SessionContext:
    client_id: str
    memory: MemoryProvider
    current_session_id: str | None

class SessionHandler:
    def __init__(self, data_dir: Path, max_context_tokens: int):
        self._data_dir = data_dir
        self._max_context_tokens = max_context_tokens
        self._contexts: dict[str, SessionContext] = {}
    
    def create_context(self, client_id: str) -> SessionContext:
        """为新连接创建独立的 SessionContext"""
        memory = create_memory_provider(
            data_dir=self._data_dir,
            max_context_tokens=self._max_context_tokens,
        )
        ctx = SessionContext(
            client_id=client_id,
            memory=memory,
            current_session_id=None,
        )
        self._contexts[client_id] = ctx
        return ctx
    
    def get_context(self, client_id: str) -> SessionContext | None:
        return self._contexts.get(client_id)
    
    def release_context(self, client_id: str) -> None:
        """释放 session 资源"""
        ctx = self._contexts.pop(client_id, None)
        if ctx:
            ctx.memory.save_session()
```

**验证方式**：
- [ ] 单元测试：创建多个 `SessionContext`，验证独立性
- [ ] 验证 `release_context()` 正确保存 session

#### 任务 1.2.4：创建 `server/transport.py` — WebSocket Server

**文件**：`server/transport.py`（新建）

**关键修正**：`_handle_connection()` 需要将 `client_id` 传递给 `handle_chat()` 和 `handle_command()`，以便工具能获取正确的 `SessionContext`。

**内容**：
```python
class BrixServer:
    """WebSocket Server — Unix Socket + 可选 TCP"""
    
    def __init__(self, app: BrixServerApp, socket_path: str = "~/.brix/server.sock"):
        self._app = app
        self._socket_path = Path(socket_path).expanduser()
        self._handler = SessionHandler(...)
        self._connections: dict[str, websockets.WebSocketServerProtocol] = {}
    
    async def start(self) -> None:
        """启动 WebSocket Server"""
        # 确保 socket 目录存在
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        # 清理旧的 socket 文件
        if self._socket_path.exists():
            self._socket_path.unlink()
        # 启动 Unix Socket server
        self._server = await websockets.serve(
            self._handle_connection,
            path=str(self._socket_path),
        )
    
    async def _handle_connection(self, websocket: websockets.WebSocketServerProtocol) -> None:
        """处理单个 WebSocket 连接"""
        client_id = str(uuid.uuid4())
        ctx = self._handler.create_context(client_id)
        self._connections[client_id] = websocket
        
        try:
            async for message in websocket:
                await self._handle_message(message, ctx, websocket)
        finally:
            self._handler.release_context(client_id)
            del self._connections[client_id]
    
    async def _handle_message(self, raw: str, ctx: SessionContext, ws: websockets.WebSocketServerProtocol) -> None:
        """处理单条消息"""
        msg = json.loads(raw)
        msg_type = msg.get("type")
        
        if msg_type == "chat":
            async for event in self._app.handle_chat(msg["content"], ctx):
                await ws.send(json.dumps(event))
        elif msg_type == "command":
            result = await self._app.handle_command(msg["command"], msg.get("args", ""), ctx)
            await ws.send(json.dumps(result))
        # ... 其他消息类型
    
    async def stop(self) -> None:
        """停止 Server"""
        self._server.close()
        await self._server.wait_closed()
        # 清理 socket 文件
        if self._socket_path.exists():
            self._socket_path.unlink()
```

**验证方式**：
- [ ] 单元测试：启动 Server，验证 socket 文件创建
- [ ] 集成测试：用 websockets 客户端连接，发送消息，验证响应
- [ ] 验证多连接并发处理

#### 任务 1.2.4：创建 `server/daemon.py` — 进程管理

**文件**：`server/daemon.py`（新建）

**内容**：
```python
class ServerDaemon:
    """Server 进程管理 — PID 文件、信号处理"""
    
    def __init__(self, pid_file: str = "~/.brix/server.pid"):
        self._pid_file = Path(pid_file).expanduser()
    
    def write_pid(self) -> None:
        """写入 PID 文件"""
        self._pid_file.parent.mkdir(parents=True, exist_ok=True)
        self._pid_file.write_text(str(os.getpid()))
    
    def read_pid(self) -> int | None:
        """读取 PID 文件"""
        if not self._pid_file.exists():
            return None
        try:
            return int(self._pid_file.read_text().strip())
        except ValueError:
            return None
    
    def is_running(self) -> bool:
        """检查 Server 是否运行中"""
        pid = self.read_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, 0)  # 检查进程是否存在
            return True
        except OSError:
            return False
    
    def cleanup(self) -> None:
        """清理 PID 文件"""
        if self._pid_file.exists():
            self._pid_file.unlink()
    
    def setup_signal_handlers(self, shutdown_callback: Callable) -> None:
        """设置信号处理器"""
        def _handler(signum, frame):
            asyncio.get_event_loop().create_task(shutdown_callback())
        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)
```

**验证方式**：
- [ ] 单元测试：写入/读取/清理 PID 文件
- [ ] 验证 `is_running()` 正确检测进程状态
- [ ] 验证信号处理器注册

#### 任务 1.2.5：创建 `server/__main__.py` — Server 入口

**文件**：`server/__main__.py`（新建）

**关键修正**：`BrixServer` 需要将 `client_id` 传递给 `handle_chat()` 和 `handle_command()`，以便工具能获取正确的 `SessionContext`。

**内容**：
```python
"""Server 入口 — 可通过 python -m server 启动"""

import asyncio
import argparse
from config.loader import load_config
from server.app import BrixServerApp
from server.transport import BrixServer
from server.daemon import ServerDaemon

def main():
    parser = argparse.ArgumentParser(description="Brix Server")
    parser.add_argument("--foreground", action="store_true", help="前台运行")
    parser.add_argument("--port", type=int, help="远程端口（可选）")
    args = parser.parse_args()
    
    config = load_config()
    app = BrixServerApp(config)
    daemon = ServerDaemon()
    
    # 检查是否已有 Server 运行
    if daemon.is_running():
        print("Server is already running")
        return
    
    # 写入 PID 文件
    daemon.write_pid()
    
    # 设置信号处理器
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def shutdown():
        await app.shutdown()
        daemon.cleanup()
        loop.stop()
    
    daemon.setup_signal_handlers(shutdown)
    
    # 启动 Server
    server = BrixServer(app, config.get("server", {}).get("socket_path", "~/.brix/server.sock"))
    loop.run_until_complete(server.start())
    
    print(f"✓ Server started. PID: {os.getpid()}")
    print(f"✓ Listening: unix://~/.brix/server.sock")
    
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(shutdown())
        loop.close()

if __name__ == "__main__":
    main()
```

**验证方式**：
- [ ] 集成测试：`python -m server --foreground` 启动 Server
- [ ] 验证 PID 文件创建和信号处理
- [ ] 验证 `Ctrl+C` 优雅关闭

---

### 3.3 阶段 3：改造 CLI 入口 (`main.py`)

**目标**：支持子命令路由：`brix serve`、`brix`、`brix stop`、`brix status`

#### 任务 1.3.1：重写 `main.py` — 子命令路由

**文件**：`main.py`（重写）

**内容**：
```python
"""Entry point for the Brix CLI."""

import os
import sys
import asyncio
import subprocess
import signal
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from config.loader import load_config
from server.daemon import ServerDaemon

def cmd_serve(foreground: bool = False, port: int | None = None):
    """启动 Server"""
    args = [sys.executable, "-m", "server"]
    if foreground:
        args.append("--foreground")
    if port:
        args.extend(["--port", str(port)])
    
    if foreground:
        # 前台运行
        os.execvp(sys.executable, args)
    else:
        # 后台启动
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # 脱离当前终端
        )
        # 等待 Server 就绪
        daemon = ServerDaemon()
        for _ in range(50):  # 最多等待 5 秒
            if daemon.is_running():
                print(f"✓ Server started. PID: {daemon.read_pid()}")
                return
            time.sleep(0.1)
        print("✗ Server failed to start")
        sys.exit(1)

def cmd_stop():
    """停止 Server"""
    daemon = ServerDaemon()
    pid = daemon.read_pid()
    if pid is None:
        print("Server is not running")
        return
    
    try:
        os.kill(pid, signal.SIGTERM)
        # 等待进程退出
        for _ in range(50):
            if not daemon.is_running():
                print("✓ Server stopped")
                return
            time.sleep(0.1)
        # 强制终止
        os.kill(pid, signal.SIGKILL)
        print("✓ Server force stopped")
    except OSError:
        print("Server is not running")
        daemon.cleanup()

def cmd_status():
    """查询 Server 状态"""
    daemon = ServerDaemon()
    pid = daemon.read_pid()
    if pid is None or not daemon.is_running():
        print("Server: ● not running")
        return
    
    # TODO: 通过 WebSocket 查询详细状态
    print(f"Server: ● running (PID: {pid})")

def cmd_tui(remote: str | None = None):
    """启动 TUI（自动检测/启动 Server）"""
    daemon = ServerDaemon()
    
    # 检查 Server 是否运行
    if not daemon.is_running():
        print("Starting server...")
        cmd_serve(foreground=False)
    
    # 启动 TUI Client
    from cli.app import BrixTUIClient
    client = BrixTUIClient(remote=remote)
    asyncio.run(client.run())

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "serve":
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument("--foreground", action="store_true")
            parser.add_argument("--port", type=int)
            args = parser.parse_args(sys.argv[2:])
            cmd_serve(args.foreground, args.port)
        elif cmd == "stop":
            cmd_stop()
        elif cmd == "status":
            cmd_status()
        elif cmd == "--remote":
            cmd_tui(remote=sys.argv[2] if len(sys.argv) > 2 else None)
        else:
            print(f"Unknown command: {cmd}")
            sys.exit(1)
    else:
        # 默认：启动 TUI
        cmd_tui()

if __name__ == "__main__":
    main()
```

**验证方式**：
- [ ] `brix serve --foreground` 前台启动 Server
- [ ] `brix serve` 后台启动 Server
- [ ] `brix stop` 优雅关闭 Server
- [ ] `brix status` 查询状态
- [ ] `brix` 自动启动 Server + TUI
- [ ] Server 已运行时，`brix` 不重复启动

---

### 3.4 阶段 4：改造 TUI 为瘦客户端 (`cli/app.py`)

**目标**：删除所有核心逻辑，改为通过 `BrixTransport` 与 Server 通信

#### 任务 1.4.1：重写 `cli/app.py` — BrixTUIClient

**文件**：`cli/app.py`（重写）

**关键改动**：

**删除**：
- `_memory: MemoryProvider`（第 68-71 行）
- `_llm_client: LLMClient`（第 72 行）
- `_tool_runner: ToolRunner`（第 73 行）
- `_orchestrator`（第 76 行）
- `_command_registry: CommandRegistry`（第 75 行）
- `_side_manager: SideTaskManager`（第 79-86 行）
- `_register_tools()`（第 637-656 行）
- `_register_commands()`（第 775-809 行）
- `_register_skill_tool()`（第 811-819 行）
- `_build_orchestrator()`（第 821-830 行）
- `_build_dynamic_context()`（第 832-847 行）
- `_process()`（第 318-378 行）
- `_process_streaming()`（第 380-632 行）的 LLM/Orchestrator 调用部分

**保留**：
- UI 渲染器：`StreamRenderer`、`ThinkingRenderer`、`ToolDisplay`、`StageIndicator`
- Voice 模块：`_init_voice()`、语音硬件控制
- 输入处理：`PromptSession`、`Banner`、`Completer`

**降级处理**：
- `StatusBar`：Phase 1 降级为静态显示（只显示 model 名称 + 连接状态），不显示 side task 运行状态。side_manager 在 server 端，TUI 无法获取实时状态。
- TODO: Phase 2（macOS 状态栏 App）通过 WebSocket 拉取 Server 状态实现完整状态栏功能。

**新增**：
```python
class BrixTUIClient:
    def __init__(self, remote: str | None = None):
        self._transport: BrixTransport | None = None
        self._remote = remote
        self._console = Console(theme=BRIX_THEME)
        self._voice: VoiceRuntimeImpl | None = None
        self._voice_display = None
        self._voice_input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._init_voice()
        
        # UI 组件（保留）
        self._status_bar_enabled = ...  # 从配置读取
        if self._status_bar_enabled:
            self._status_bar_renderer = ...
    
    async def _ensure_server(self) -> None:
        """确保 Server 正在运行"""
        from server.daemon import ServerDaemon
        daemon = ServerDaemon()
        if not daemon.is_running():
            # 自动启动 Server
            subprocess.Popen(
                [sys.executable, "-m", "server"],
                start_new_session=True,
            )
            # 等待就绪
            for _ in range(50):
                if daemon.is_running():
                    break
                await asyncio.sleep(0.1)
    
    async def _connect(self) -> None:
        """连接 Server"""
        if self._remote:
            host, port = self._remote.split(":")
            self._transport = BrixTransport.remote(host, int(port))
        else:
            self._transport = BrixTransport.local()
        await self._transport.connect()
    
    async def run(self) -> None:
        """REPL 主循环"""
        await self._ensure_server()
        await self._connect()
        
        # 渲染 Banner
        show_banner(...)
        
        # 设置状态栏
        if self._status_bar_enabled:
            setup_scroll_region(status_lines=1)
            paint_status_bar(self._status_bar_renderer)
        
        try:
            while True:
                # 等待键盘输入或语音输入
                text = await self._read_input()
                
                if not text:
                    continue
                
                # Slash commands
                if text.startswith("/"):
                    await self._handle_command(text)
                    continue
                
                # 普通消息
                await self._send_chat_and_render(text)
        finally:
            if self._voice and self._voice.is_running:
                await self._voice.stop()
            if self._status_bar_enabled:
                teardown_scroll_region()
    
    async def _send_chat_and_render(self, content: str) -> None:
        """发送 chat 消息，接收流式事件并渲染"""
        renderer = None
        thinking_renderer = None
        tool_display = ToolDisplay(self._console)
        
        async for event in self._transport.send_chat(content):
            event_type = event.get("type")
            
            if event_type == "thinking_delta":
                if thinking_renderer is None:
                    thinking_renderer = ThinkingRenderer(self._console)
                    thinking_renderer.start()
                thinking_renderer.push_delta(event.get("text", ""))
            
            elif event_type == "text_delta":
                if thinking_renderer is not None:
                    thinking_renderer.flush()
                    thinking_renderer = None
                if renderer is None:
                    renderer = StreamRenderer(self._console, marker=Text("⏺ ", style="green"))
                    renderer.start()
                renderer.push_delta(event.get("text", ""))
            
            elif event_type == "tool_call":
                if renderer is not None:
                    renderer.flush()
                    renderer = None
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
            
            elif event_type == "stream_end":
                break
        
        # 清理
        if thinking_renderer is not None:
            thinking_renderer.flush()
        if renderer is not None:
            renderer.flush()
        tool_display.cleanup()
    
    async def _handle_command(self, text: str) -> None:
        """处理 slash 命令"""
        parts = text.split()
        cmd_name = parts[0].lstrip("/")
        args = " ".join(parts[1:]) if len(parts) > 1 else ""
        
        result = await self._transport.send_command(cmd_name, args)
        
        # 客户端处理副作用
        if cmd_name == "quit":
            # 不 sys.exit，而是断开连接
            await self._transport.close()
            return
        
        if cmd_name == "resume":
            # 用 PaginatedSelector 渲染 session 列表
            sessions = result.get("data", {}).get("sessions", [])
            if sessions:
                # PaginatedSelector 需要 items 和 format_item 参数
                selector = PaginatedSelector(
                    items=sessions,
                    format_item=lambda s, idx: f"{s.get('title', 'Untitled')} ({s.get('message_count', 0)} msgs)",
                    title="选择一个会话",
                )
                selected = await selector.prompt_async()
                if selected:
                    resume_result = await self._transport.send_command("resume", selected["id"])
                    # 渲染历史消息
                    messages = resume_result.get("data", {}).get("messages", [])
                    render_history(self._console, messages)
        
        # 其他命令：直接显示结果
        self._console.print(result.get("data", {}))
```

**验证方式**：
- [ ] TUI 启动后自动连接 Server
- [ ] 正常对话（thinking、文本、tool call 渲染正常）
- [ ] `/resume` 显示 session 列表并可选择
- [ ] `/clear` 清空当前 session
- [ ] `/quit` 断开连接而非 `sys.exit`
- [ ] Voice 输入通过 `voice_input` 消息发送给 Server
- [ ] 关闭 TUI 后 Server 继续运行

---

### 3.5 阶段 5：集成测试与验收

**目标**：验证所有功能正常工作

#### 任务 1.5.1：端到端测试

**测试场景**：
1. **Server 启动**
   - `brix serve --foreground` 前台启动
   - `brix serve` 后台启动
   - `brix stop` 优雅关闭
   - `brix status` 查询状态

2. **TUI 连接**
   - `brix` 自动启动 Server + TUI
   - Server 已运行时直接连接
   - 多个 TUI 实例同时连接

3. **对话功能**
   - 普通对话（无 tool call）
   - 带 tool call 的对话
   - thinking 折叠
   - 流式输出

4. **Slash 命令**
   - `/resume` 恢复历史 session
   - `/clear` 清空当前 session
   - `/model list` 列出模型
   - `/quit` 断开连接

5. **Voice 功能**
   - 语音输入 → Client STT → `voice_input` 消息 → Server 处理 → 回复 → Client TTS

6. **Session 管理**
   - 多个 TUI 实例独立 session
   - 关闭 TUI 后重新连接，session 保留
   - Server 重启后 session 恢复

**验证方式**：
- [ ] 手动测试所有场景
- [ ] 编写自动化测试脚本
- [ ] 记录测试结果

---

## 四、配置变更

### 4.1 新增 Server 配置

**文件**：`config/settings.yaml`（追加）

```yaml
# ============================================================
# Server 配置
# ============================================================
server:
  # Unix socket 路径
  socket_path: "~/.brix/server.sock"
  
  # PID 文件路径
  pid_file: "~/.brix/server.pid"
  
  # 远程访问（默认禁用）
  remote:
    enabled: false
    host: "0.0.0.0"
    port: 8080
```

### 4.2 不变配置

- `providers`、`models`、`routing`、`retry` — 完全不变
- `memory` — 完全不变
- `side` — 完全不变
- `voice` — 移到客户端配置（每个客户端独立配置）
- `engine` — 完全不变
- `status_bar` — 属于 TUI 客户端配置

---

## 五、依赖变更

### 5.1 新增依赖

**文件**：`pyproject.toml`（追加）

```toml
[project.optional-dependencies]
server = [
    "websockets>=12.0",
]
```

### 5.2 安装方式

```bash
# 安装 server 依赖
pip install -e ".[server]"

# 或者单独安装
pip install websockets
```

---

## 六、风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| **BrixCLI 逻辑迁移复杂** | 逐个方法迁移，保持原有逻辑不变，只去掉 UI 调用 |
| **WebSocket 连接不稳定** | 添加重连机制，Server 崩溃时 Client 显示 "Connection lost" |
| **多 Client 并发写 session** | fcntl 文件锁保护，不同 session 文件无冲突 |
| **Server 启动失败** | 详细的错误日志，超时检测，进程清理 |
| **Voice 模块在 Client 侧** | 确保 Voice 配置正确迁移到 Client，不依赖 Server |

---

## 七、验收清单

### 7.1 功能验收

- [ ] `brix serve` 启动后，Server 作为独立后台进程运行
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

### 7.2 代码质量验收

- [ ] 代码符合项目规范（中文注释、类型标注、异步优先）
- [ ] 新增模块有单元测试
- [ ] 关键路径有集成测试
- [ ] 文档完整（README、docstring、设计文档更新）

---

## 八、工作量预估

| 阶段 | 任务 | 预估工时 | 依赖 |
|------|------|---------|------|
| 1.1 | 协议层 | 2-3 小时 | 无 |
| 1.2 | Server 核心 | 8-10 小时 | 1.1 |
| 1.3 | CLI 入口 | 3-4 小时 | 1.2 |
| 1.4 | TUI 瘦身 | 6-8 小时 | 1.2 |
| 1.5 | 集成测试 | 4-6 小时 | 1.3, 1.4 |
| **总计** | | **23-31 小时** | |

**建议**：按 1.1 → 1.2 → 1.3 → 1.4 → 1.5 顺序推进，每个阶段完成后进行验证。

---

## 九、下一步行动

1. **审批本计划** — 确认任务拆解、技术选型、工作量预估
2. **开始实施** — 从 1.1 协议层开始
3. **持续验证** — 每个阶段完成后进行测试
4. **迭代优化** — 根据实际情况调整计划

---

**计划版本**: 1.0  
**最后更新**: 2026-06-28  
**状态**: 待审批
