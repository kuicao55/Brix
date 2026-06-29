"""BrixTUIClient — TUI 瘦客户端，通过 WebSocket 与 Server 通信。"""

from __future__ import annotations

import asyncio
import sys
import subprocess
from pathlib import Path
from typing import Any

from prompt_toolkit import HTML, PromptSession
from prompt_toolkit.completion import FuzzyCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.text import Text

from cli.banner import show_banner
from cli.completer import SlashCommandCompleter
from cli.display import render_history
from cli.paginated_selector import PaginatedSelector
from cli.stage_indicator import StageIndicator
from cli.ansi_status_bar import paint_status_bar, setup_scroll_region, teardown_scroll_region
from cli.status_bar import StatusBarRenderer
from cli.stream_renderer import StreamRenderer
from cli.thinking_renderer import ThinkingRenderer
from cli.theme import BRIX_THEME
from cli.tool_display import ToolDisplay
from config.loader import load_config
from protocol.transport import BrixTransport
from protocol.types import ServerEvent


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

    def __init__(self, remote: str | None = None) -> None:
        self._config = load_config()
        self._transport: BrixTransport | None = None
        self._remote = remote
        self._console = Console(theme=BRIX_THEME)
        self._voice = None
        self._voice_display = None
        self._voice_input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._init_voice()

        # 状态栏（Phase 1 降级为静态显示）
        self._status_bar_enabled = self._config.get("status_bar", {}).get("enabled", False)
        if self._status_bar_enabled:
            self._status_bar_renderer = StatusBarRenderer(None)  # 不绑定 side_model
            # Phase 1: 状态栏只显示连接状态和模型名
            # TODO: Phase 2 通过 WebSocket 拉取 Server 状态

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _resolve_model(self) -> str:
        """解析主模型：default_model → fallback_model → 空字符串。"""
        routing = self._config.get("routing", {})
        return routing.get("default_model", "") or routing.get("fallback_model", "")

    def _repaint_status_bar(self) -> None:
        """重绘 ANSI 状态栏（固定在终端最后一行）。"""
        if not self._status_bar_enabled or not self._status_bar_renderer:
            return
        try:
            paint_status_bar(self._status_bar_renderer)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Voice 初始化（保留，语音硬件在客户端）
    # ------------------------------------------------------------------

    def _init_voice(self) -> None:
        """初始化语音模块（如果配置启用）。"""
        voice_cfg = self._config.get("voice", {})
        if not voice_cfg.get("enabled", False):
            return
        try:
            from capability.voice.config import VoiceConfig
            from capability.voice.runtime import VoiceRuntimeImpl
            from capability.voice.tts.cosyvoice_client import create_cosyvoice_client
            from hooks.registry import HookRegistry

            cfg = VoiceConfig.from_dict(self._config)

            # 创建 TTS 客户端（可选，API key 缺失时跳过）
            tts_client = create_cosyvoice_client(self._config)

            # 包装 LLM 调用：cleanup 用轻量模型
            # 注意：客户端不直接调用 LLM，需要通过 Server
            # Phase 1: 暂时禁用 cleanup 功能
            async def _cleanup_llm(prompt: str) -> str:
                # TODO: 通过 WebSocket 发送给 Server 处理
                return prompt

            self._voice = VoiceRuntimeImpl(
                config=cfg,
                hooks=HookRegistry(),
                llm_fn=_cleanup_llm,
                tts_client=tts_client,
            )
            self._voice.on_voice_input(self._handle_voice_input)

            # 注册实时显示回调
            from cli.voice_display import VoiceDisplay

            self._voice_display = VoiceDisplay(self._console)
            self._voice.on_state_change(self._handle_voice_state)
            self._voice.on_interim_text(self._handle_interim_text)
            # timing hook
            self._voice._hooks.register("voice_timing", self._handle_voice_timing)
            self._voice._hooks.register("voice_tts_queue", self._handle_voice_tts_queue)
            self._voice._hooks.register("voice_tts_skip", self._handle_voice_tts_skip)
            self._voice._hooks.register("voice_tts", self._handle_voice_tts)
            self._voice._hooks.register("voice_tts_error", self._handle_voice_tts_error)
        except Exception as exc:
            self._console.print(f"[dim]语音模块加载失败: {exc}[/]")

    def _handle_voice_input(self, text: str) -> None:
        """语音输入回调 — 将文本注入 REPL 循环。"""
        if self._voice_display:
            self._voice_display.finish(text)
        self._voice_input_queue.put_nowait(text)

    def _handle_voice_state(self, state: str) -> None:
        """语音状态变化回调 — 更新 VoiceDisplay。"""
        if not self._voice_display:
            return
        if state == "listening":
            self._voice_display.start_listening()
        elif state in ("idle", "error"):
            self._voice_display.stop()

    def _handle_interim_text(self, text: str) -> None:
        """Interim 转录回调 — 实时更新 VoiceDisplay。"""
        if self._voice_display:
            self._voice_display.update_interim(text)

    def _handle_voice_timing(self, event: Any) -> None:
        """Voice timing hook — 更新 VoiceDisplay 的耗时显示。"""
        if self._voice_display:
            step = event.data.get("step", "")
            ms = event.data.get("ms", 0)
            self._voice_display.update_timing(step, ms)

    def _handle_voice_tts(self, event: Any) -> None:
        """TTS 成功回调 — 输出简短诊断信息。"""
        backend = event.data.get("backend", "unknown")
        chunks = event.data.get("chunks", 0)
        bytes_ = event.data.get("bytes", 0)
        self._console.print(
            f"[dim]TTS ok: backend={backend}, chunks={chunks}, bytes={bytes_}[/]"
        )

    def _handle_voice_tts_error(self, event: Any) -> None:
        """TTS 错误回调 — 输出可见错误。"""
        error = event.data.get("error", "unknown")
        backend = event.data.get("backend", "unknown")
        self._console.print(
            f"[yellow]TTS error: {error} (backend={backend})[/]"
        )

    def _handle_voice_tts_queue(self, event: Any) -> None:
        source = event.data.get("source", "unknown")
        text = event.data.get("text", "")
        self._console.print(
            f"[dim]TTS queue: source={source}, text='{text}'[/]"
        )

    def _handle_voice_tts_skip(self, event: Any) -> None:
        source = event.data.get("source", "unknown")
        text = event.data.get("text", "")
        self._console.print(
            f"[dim]TTS skip: source={source}, text='{text}'[/]"
        )

    # ------------------------------------------------------------------
    # Server 连接
    # ------------------------------------------------------------------

    async def _ensure_server(self) -> None:
        """确保 Server 正在运行。未运行时自动后台启动。"""
        from server.daemon import ServerDaemon

        daemon = ServerDaemon(
            pid_file=self._config.get("server", {}).get("pid_file", "~/.brix/server.pid")
        )
        if not daemon.is_running():
            self._console.print("[dim]Starting server...[/]")
            args = [sys.executable, "-m", "server"]
            subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            # 等待就绪
            for _ in range(50):
                if daemon.is_running():
                    break
                await asyncio.sleep(0.1)
            else:
                self._console.print("[red]✗ Server failed to start[/]")
                sys.exit(1)
            self._console.print("[dim]✓ Server ready[/]")

    async def _connect(self) -> None:
        """通过 Unix Socket 连接 server，建立 WebSocket。"""
        if self._remote:
            host, port = self._remote.split(":")
            self._transport = BrixTransport.remote(host, int(port))
        else:
            socket_path = self._config.get("server", {}).get("socket_path", "~/.brix/server.sock")
            self._transport = BrixTransport.local(socket_path)

        try:
            await self._transport.connect()
        except Exception as exc:
            self._console.print(f"[red]✗ Connection failed: {exc}[/]")
            sys.exit(1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """REPL 主循环。"""
        await self._ensure_server()
        await self._connect()

        completer = FuzzyCompleter(SlashCommandCompleter(None))  # 不绑定 command_registry
        # 补全菜单样式：纯文字，无背景无边框
        completion_style = Style.from_dict({
            "completion-menu": "bg:",
            "completion-menu.completion": "fg:#888888 bg:",
            "completion-menu.completion.current": "fg:#000000 bg:",
            "completion-menu.meta.completion": "fg:#666666 bg:",
            "completion-menu.meta.completion.current": "fg:#333333 bg:",
            "completion-menu.multi-column-meta": "bg:",
            "completion-menu.completion fuzzymatch.inside": "bg:",
            "completion-menu.completion fuzzymatch.inside.character": "bg:",
            "completion-menu.completion fuzzymatch.outside": "fg:#666666 bg:",
            "scrollbar": "bg:",
            "scrollbar.button": "bg:",
        })
        session = PromptSession(
            history=InMemoryHistory(),
            completer=completer,
            complete_while_typing=True,
            style=completion_style,
        )
        default_model = self._config.get("routing", {}).get("default_model", "unknown")

        # 状态栏：设置 ANSI 滚动区域，保留底部 1 行给状态栏
        if self._status_bar_enabled:
            setup_scroll_region(status_lines=1)
            self._repaint_status_bar()

        show_banner(console=self._console, model=default_model, version="0.2.0", cwd=str(Path.cwd()))

        first_turn = True
        try:
            while True:
                if not first_turn:
                    self._console.print()
                first_turn = False

                # 并行等待键盘输入和语音输入
                keyboard_task = asyncio.create_task(
                    session.prompt_async(HTML('<ansicyan><b>❯ </b></ansicyan>'))
                )
                voice_task = asyncio.create_task(self._voice_input_queue.get())

                try:
                    done, pending = await asyncio.wait(
                        [keyboard_task, voice_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                except (KeyboardInterrupt, asyncio.CancelledError):
                    keyboard_task.cancel()
                    voice_task.cancel()
                    break

                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass

                if voice_task in done:
                    text = voice_task.result()
                elif keyboard_task in done:
                    try:
                        text = keyboard_task.result()
                    except (EOFError, KeyboardInterrupt):
                        self._console.print("\n[dim]Goodbye.[/]")
                        break
                else:
                    continue

                text = text.strip()
                if not text:
                    continue

                # Slash commands
                if text.startswith("/"):
                    if await self._handle_command(text):
                        continue
                    # /quit 返回 False，退出循环

                # Normal message — stream response
                self._console.print()  # ❯ 和 ⏺ 之间的间隔
                try:
                    await self._send_chat_and_render(text)
                except KeyboardInterrupt:
                    self._console.print("\n[dim]Goodbye.[/]")
                    break
                except Exception as exc:
                    self._console.print("[red]Error:[/] {}".format(exc))
        finally:
            if self._voice and self._voice.is_running:
                await self._voice.stop()
            if self._transport:
                await self._transport.close()
            if self._status_bar_enabled:
                teardown_scroll_region()

    # ------------------------------------------------------------------
    # Command handling
    # ------------------------------------------------------------------

    async def _handle_command(self, text: str) -> bool:
        """Handle slash commands. Returns True to continue the loop."""
        parts = text.split()
        cmd_name = parts[0].lower().lstrip("/")
        args = " ".join(parts[1:]) if len(parts) > 1 else ""

        # 向后兼容：/exit 映射到 /quit
        if cmd_name == "exit":
            cmd_name = "quit"

        # 特殊处理：/quit 不需要发给 Server
        if cmd_name == "quit":
            self._console.print("\n[dim]Goodbye.[/]")
            return False

        # 发送给 Server 处理
        try:
            result = await self._transport.send_command(cmd_name, args)
        except Exception as exc:
            self._console.print(f"[red]Command error: {exc}[/]")
            return True

        # 处理结果
        if result.type == "error":
            self._console.print(f"[red]{result.message}[/]")
            return True

        data = result.data or {}

        # 特殊处理：/resume
        if cmd_name == "resume":
            # 直接恢复（有 args 匹配到唯一 session）
            if data.get("resumed_session_id"):
                messages = data.get("messages", [])
                if messages:
                    self._console.print()
                    render_history(self._console, messages)
                return True

            # 交互式选择
            sessions = data.get("sessions", [])
            if not sessions:
                self._console.print("[dim]No sessions found.[/]")
                return True

            # 用 PaginatedSelector 渲染 session 列表
            selector = PaginatedSelector(
                items=sessions,
                format_item=lambda s, idx: f"{s.get('title', 'Untitled')} ({s.get('message_count', 0)} msgs)",
                title="选择一个会话",
            )
            selected = await selector.prompt_async()
            if selected:
                # 恢复选中的 session
                resume_result = await self._transport.resume_session(selected["id"])
                if resume_result.type == "error":
                    self._console.print(f"[red]{resume_result.message}[/]")
                else:
                    messages = resume_result.data.get("messages", [])
                    if messages:
                        self._console.print()
                        render_history(self._console, messages)
            return True

        # 特殊处理：/clear
        if cmd_name == "clear":
            # 创建新 session
            await self._transport.create_session()
            self._console.print("[dim]Session cleared.[/]")
            return True

        # 特殊处理：/help
        if cmd_name == "help":
            help_text = data.get("text", "")
            if help_text:
                self._console.print(help_text)
            return True

        # 其他命令：显示结果
        if data:
            self._console.print(data)

        return True

    # ------------------------------------------------------------------
    # Chat streaming
    # ------------------------------------------------------------------

    async def _send_chat_and_render(self, content: str) -> None:
        """发送 chat 消息，接收流式事件并用 UI 渲染器渲染。"""
        renderer = None
        thinking_renderer = None
        content_parts = []
        tool_display = ToolDisplay(self._console)

        try:
            async for event in self._transport.send_chat(content):
                event_type = event.type

                if event_type == "thinking_delta":
                    text = event.text
                    if text:
                        if thinking_renderer is None:
                            tool_display.stop_thinking()
                            thinking_renderer = ThinkingRenderer(self._console)
                            thinking_renderer.start()
                        thinking_renderer.push_delta(text)

                elif event_type == "text_delta":
                    text = event.text
                    if text:
                        # thinking 结束，切换到正式文本渲染
                        if thinking_renderer is not None:
                            thinking_renderer.flush()
                            thinking_renderer = None
                        if renderer is None:
                            tool_display.stop_thinking()
                            renderer = StreamRenderer(
                                self._console,
                                marker=Text("⏺ ", style="green"),
                            )
                            renderer.start()
                        renderer.push_delta(text)
                        content_parts.append(text)

                elif event_type == "tool_call":
                    if thinking_renderer is not None:
                        thinking_renderer.flush()
                        thinking_renderer = None
                    if renderer is not None:
                        renderer.flush()
                        renderer = None
                    self._console.print()  # 工具调用前的间隔
                    tool_display.show_tool_start(
                        event.name, event.input
                    )

                elif event_type == "tool_result":
                    tool_display.show_tool_result(
                        event.name,
                        event.result,
                        event.ms,
                        is_error=event.is_error,
                    )
                    self._console.print()  # 工具结果后的间隔

                elif event_type == "error":
                    self._console.print(f"[red]Error:[/] {event.message}")

                elif event_type == "stream_end":
                    break

        except Exception as exc:
            if thinking_renderer is not None:
                thinking_renderer.flush()
                thinking_renderer = None
            if renderer is not None:
                renderer.flush()
                renderer = None
            err_text = str(exc).split("\n")[0].strip()
            if len(err_text) > 200:
                err_text = err_text[:199] + "…"
            self._console.print("[red]Error:[/] {}".format(err_text))

        finally:
            tool_display.cleanup()
            self._repaint_status_bar()

        # Flush any remaining content
        if thinking_renderer is not None:
            thinking_renderer.flush()
        if renderer is not None:
            renderer.flush()

        response = "".join(content_parts)

        # TTS 桥接：统一在完整回复后一次性触发
        if (
            self._voice
            and self._voice.is_running
            and self._voice.output_enabled
            and response.strip()
        ):
            self._console.print(f"[dim]TTS trigger: chars={len(response)}[/]")
            self._voice.feed_response_text(response)
            self._voice.flush_tts()


# 向后兼容别名
BrixCLI = BrixTUIClient
