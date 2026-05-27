"""Interactive REPL for Brix."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from prompt_toolkit import HTML, PromptSession
from prompt_toolkit.completion import FuzzyCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.shortcuts.choice_input import ChoiceInput
from rich.console import Console

from capability.runner import ToolRunner
from capability.basics.sessions import list_sessions, get_session_by_prefix, resume_session
from capability.basics.memory_files import load_soul, load_user
from capability.basics.logs import get_recent_logs, get_log_detail
from capability.basics.commands import get_command_list
from capability.command.base import CommandContext, CommandResultType
from capability.command.registry import CommandRegistry
from hooks.registry import HookRegistry
from capability.tools.bash import BashTool
from capability.tools.calculator import CalculatorTool
from capability.tools.file_edit import FileEditTool
from capability.tools.file_read import FileReadTool
from capability.tools.file_write import FileWriteTool
from capability.tools.skill_tool import SkillTool
from capability.tools.weather import WeatherTool
from cli.banner import show_banner
from cli.completer import SlashCommandCompleter
from cli.display import render_history
from cli.paginated_selector import PaginatedSelector
from cli.stage_indicator import StageIndicator
from cli.stream_renderer import StreamRenderer
from cli.thinking_renderer import ThinkingRenderer
from cli.theme import BRIX_THEME
from cli.tool_display import ToolDisplay
from config.loader import load_config
from log.flow import FlowLog
from log.writer import flush_log
from infra.llm_client import LLMClient
from memory import MemoryProvider, create_memory_provider
from orchestrator.engine import OrchestratorContext
from orchestrator.state_machine import StateMachineOrchestrator
from side.manager import SideTaskManager
from side.tasks import ALL_TASKS


class BrixCLI:
    """REPL interface that wires memory, routing, orchestrator, and tools."""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config if config is not None else load_config()
        self._data_dir = self._config.get("memory", {}).get("data_dir", "memory/data")
        max_tokens = self._config.get("memory", {}).get("max_context_tokens", 8000)
        self._memory: MemoryProvider = create_memory_provider(
            data_dir=self._data_dir,
            max_context_tokens=max_tokens,
        )
        self._llm_client = LLMClient(self._config)
        self._tool_runner = ToolRunner()
        self._register_tools()
        self._command_registry = CommandRegistry()
        self._orchestrator = self._build_orchestrator()
        self._console = Console(theme=BRIX_THEME)
        # SideTaskManager 初始化（需在 _init_voice 前，voice cleanup 依赖 get_side_model）
        self._side_manager = SideTaskManager()
        self._side_manager.configure(
            config=self._config,
            llm_client=self._llm_client,
            memory=self._memory,
        )
        for task in ALL_TASKS:
            self._side_manager.register(task)
        # 语音模块（可选，需在注册命令前初始化）
        self._voice = None
        self._voice_display = None
        self._voice_input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._init_voice()
        self._register_commands()
        self._register_skill_tool()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start the REPL loop."""
        completer = FuzzyCompleter(SlashCommandCompleter(self._command_registry))
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
        show_banner(console=self._console, model=default_model, version="0.1.0", cwd=str(Path.cwd()))

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
                        self._memory.save_session()
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
                    # /quit returns True from _handle_command after printing

                # Normal message — stream response
                self._console.print()  # ❯ 和 ⏺ 之间的间隔
                try:
                    await self._process_streaming(text)
                except Exception as exc:
                    self._console.print("[red]Error:[/] {}".format(exc))
        finally:
            if self._voice and self._voice.is_running:
                await self._voice.stop()
            await self._llm_client.close()

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

        command = self._command_registry.get(cmd_name)
        if not command:
            print(f"Unknown command: /{cmd_name}")
            return True

        ctx = CommandContext(
            session_id="",
            data_dir=self._data_dir,
            console=self._console,
            config=self._config,
            memory=self._memory,
            llm_client=self._llm_client,
        )

        result = await command.execute(args, ctx)

        if result.type == CommandResultType.QUIT:
            return False
        elif result.type == CommandResultType.CLEAR:
            pass
        elif result.type == CommandResultType.PROMPT:
            self._console.print()
            await self._process_streaming(result.prompt_text)
        # NONE: 无后续操作

        return True

    def _print_resumed_messages(self, session_id: str) -> None:
        """恢复 session 并用完整聊天 UI 渲染历史对话。"""
        try:
            msgs = resume_session(self._memory, session_id)
            self._console.print(f"[dim]Resumed session {session_id[:8]}... ({len(msgs)} messages)[/]")
            if msgs:
                self._console.print()
                render_history(self._console, msgs)
        except FileNotFoundError:
            print(f"Session not found: {session_id[:8]}...")

    # ------------------------------------------------------------------
    # Core processing pipeline
    # ------------------------------------------------------------------

    async def _process(self, user_input: str) -> str:
        """Classify, route, run orchestrator, and persist."""
        log = FlowLog(user_input)
        hooks = HookRegistry()
        hooks.bind_log(log)

        dynamic_ctx = self._build_dynamic_context()
        system_prompt = self._memory.build_system_prompt(dynamic_context=dynamic_ctx)
        # 注入 Skill 列表到 system prompt
        skill_listing = self._command_registry.get_skill_listing_text()
        if skill_listing:
            system_prompt = system_prompt + "\n\n" + skill_listing
        context_messages = self._memory.get_context_messages(system_prompt)

        hooks.fire("memory", msgs=len(context_messages),
                 chars=sum(len(m.get("content", "")) for m in context_messages))

        # 直接使用 config 中的主模型
        model = self._config.get("routing", {}).get("default_model", "")
        hooks.fire("router", model=model, reason="direct_config")
        log.set_model(model)

        context = OrchestratorContext(
            history=list(context_messages),
            tool_runner=self._tool_runner,
            llm_client=self._llm_client,
            model=model,
            hooks=hooks,
        )

        # 记录 history 长度，用于提取本轮新增消息
        original_history_count = len(context.history)

        try:
            response = await self._orchestrator.run(user_input, context)
        except Exception as exc:
            log.set_error(str(exc))
            try:
                flush_log(log)
            except Exception:
                pass
            raise

        if response.startswith("Error"):
            log.set_error(response)

        # 持久化本轮新增的完整消息（包含 tool_calls、reasoning_content 等）
        if not response.startswith("Error"):
            new_messages = context.history[original_history_count:]
            for msg in new_messages:
                if msg.get("role") != "system":
                    self._memory.add_full_message(msg)
        self._memory.save_session()
        hooks.fire("persist", saved=2 if not response.startswith("Error") else 1)

        try:
            flush_log(log)
        except Exception:
            pass

        return response

    async def _process_streaming(self, user_input: str) -> None:
        """Stream orchestrator output with unified spinner and markdown rendering."""
        import time as _time
        _t_start = _time.monotonic()
        _timing = []  # (label, elapsed_ms)

        def _tick(label: str):
            _timing.append((label, int((_time.monotonic() - _t_start) * 1000)))

        indicator = StageIndicator(self._console)

        log = FlowLog(user_input)
        hooks = HookRegistry()
        hooks.bind_log(log)

        # Memory stage — build system prompt and context via MemoryProvider
        dynamic_ctx = self._build_dynamic_context()
        system_prompt = self._memory.build_system_prompt(dynamic_context=dynamic_ctx)
        # 注入 Skill 列表到 system prompt
        skill_listing = self._command_registry.get_skill_listing_text()
        if skill_listing:
            system_prompt = system_prompt + "\n\n" + skill_listing
        context_messages = self._memory.get_context_messages(system_prompt)
        hooks.fire("memory", msgs=len(context_messages),
                   chars=sum(len(m.get("content", "")) for m in context_messages))
        _tick("memory")

        # Side 层：历史搜索（如果触发）
        if self._side_manager and self._side_manager.enabled:
            indicator.update("Side", "history_search")
            search_results = await self._side_manager.run_task(
                "history_search",
                session_messages=context_messages,
                user_input=user_input,
                hooks=hooks,
            )
            if search_results:
                search_summary = "\n".join(
                    f"- {s.get('title', '无标题')}: {s.get('summary', '')[:100]}"
                    for s in search_results
                )
                context_messages.append({
                    "role": "user",
                    "content": f"[系统] 以下是你之前的对话，可能与当前问题相关：\n{search_summary}",
                })
            _tick("side:history_search")

        # 直接使用 config 中的主模型
        model = self._config.get("routing", {}).get("default_model", "")
        hooks.fire("router", model=model, reason="direct_config")
        log.set_model(model)

        # 用户消息计数（用于 pref_detection 间隔）
        if self._side_manager:
            self._side_manager.on_user_message()

        context = OrchestratorContext(
            history=list(context_messages),
            tool_runner=self._tool_runner,
            llm_client=self._llm_client,
            model=model,
            hooks=hooks,
        )

        # 记录 history 长度，用于提取本轮新增消息
        original_history_count = len(context.history)

        # Planning stage
        indicator.update("Planning", model.split("/")[-1])

        renderer = None
        thinking_renderer = None
        content_parts = []
        has_error = False
        tool_display = ToolDisplay(self._console)

        try:
            async for event in self._orchestrator.run_stream(user_input, context):
                event_type = event.get("type", "")

                if event_type == "thinking_delta":
                    text = event.get("text", "")
                    if text:
                        if thinking_renderer is None:
                            tool_display.stop_thinking()
                            indicator.stop_silent()
                            thinking_renderer = ThinkingRenderer(self._console)
                            thinking_renderer.start()
                        thinking_renderer.push_delta(text)

                elif event_type == "text_delta":
                    text = event.get("text", "")
                    if text:
                        # thinking 结束，切换到正式文本渲染
                        if thinking_renderer is not None:
                            thinking_renderer.flush()
                            thinking_renderer = None
                        if renderer is None:
                            _tick("first_token")
                            tool_display.stop_thinking()
                            indicator.stop_silent()
                            from rich.text import Text
                            renderer = StreamRenderer(
                                self._console,
                                marker=Text("⏺ ", style="green"),
                            )
                            renderer.start()
                        renderer.push_delta(text)
                        content_parts.append(text)

                elif event_type == "tool_call":
                    indicator.finish()
                    if thinking_renderer is not None:
                        thinking_renderer.flush()
                        thinking_renderer = None
                    if renderer is not None:
                        renderer.flush()
                        renderer = None
                    self._console.print()  # 工具调用前的间隔
                    tool_name = event.get("name", "unknown")
                    tool_display.show_tool_start(
                        tool_name, event.get("input", {})
                    )

                elif event_type == "tool_result":
                    tool_name = event.get("name", "unknown")
                    elapsed_ms = event.get("ms", 0)
                    is_err = event.get("is_error", False)
                    tool_display.show_tool_result(
                        tool_name,
                        event.get("result", ""),
                        elapsed_ms,
                        is_error=is_err,
                    )
                    self._console.print()  # 工具结果后的间隔

                # fire-and-forget 工具摘要
                if (event_type == "tool_result"
                        and self._side_manager and self._side_manager.enabled):
                    # NOTE: fire-and-forget 任务的返回值当前被丢弃。
                    # 后续版本需要添加 result sink（如回调或 dispatcher）来持久化任务输出。
                    self._side_manager.fire_and_forget(
                        "tool_summary",
                        session_messages=context_messages,
                        user_input=user_input,
                        hooks=hooks,
                        tool_name=tool_name,
                        tool_input=event.get("input", ""),
                        tool_result=event.get("result", ""),
                    )

        except Exception as exc:
            has_error = True
            if thinking_renderer is not None:
                thinking_renderer.flush()
                thinking_renderer = None
            if renderer is not None:
                renderer.flush()
                renderer = None
            log.set_error(str(exc))
            self._console.print("[red]Error:[/] {}".format(exc))

        finally:
            tool_display.cleanup()  # 确保异常时 spinner 被清理
            indicator.finish()

        # Flush any remaining content
        if thinking_renderer is not None:
            thinking_renderer.flush()
        if renderer is not None:
            renderer.flush()
        _tick("stream_end")

        response = "".join(content_parts)

        # TTS 桥接：统一在完整回复后一次性触发，避免流式碎片丢失触发
        if (self._voice and self._voice.is_running
                and self._voice.output_enabled and response.strip()):
            self._console.print(f"[dim]TTS trigger: chars={len(response)}[/]")
            self._voice.feed_response_text(response)
            self._voice.flush_tts()

        # Write timing data for analysis
        try:
            with open("/tmp/brix_timing.log", "a") as _f:
                _f.write("input: {}\n".format(user_input[:60]))
                for label, ms in _timing:
                    prev = 0
                    for _, p in _timing:
                        if _ is label:
                            break
                        prev = p
                    _f.write("  {:>12}: {:>5}ms  (+{}ms)\n".format(label, ms, ms - prev))
                _f.write("\n")
        except Exception:
            pass

        if response.startswith("Error"):
            has_error = True
            log.set_error(response)

        # 持久化本轮新增的完整消息（包含 tool_calls、reasoning_content 等）
        if not has_error:
            new_messages = context.history[original_history_count:]
            for msg in new_messages:
                if msg.get("role") != "system":
                    self._memory.add_full_message(msg)
        self._memory.save_session()
        hooks.fire("persist", saved=2 if not has_error else 1)

        # 偏好检测（按间隔触发）
        # NOTE: fire-and-forget 任务的返回值当前被丢弃。
        # 后续版本需要添加 result sink（如回调或 dispatcher）来持久化任务输出。
        if (self._side_manager and self._side_manager.enabled
                and self._side_manager.should_run_pref_detection()):
            self._side_manager.fire_and_forget(
                "pref_detection",
                session_messages=context_messages,
                user_input=user_input,
                hooks=hooks,
            )

        try:
            flush_log(log)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_tools(self) -> None:
        """Register all built-in tools."""
        data_root = Path(self._data_dir)
        self._tool_runner.register(BashTool())
        self._tool_runner.register(CalculatorTool())
        self._tool_runner.register(WeatherTool())
        self._tool_runner.register(FileReadTool())
        self._tool_runner.register(FileWriteTool(allowed_root=data_root))
        self._tool_runner.register(FileEditTool(allowed_root=data_root))

    def _init_voice(self) -> None:
        """初始化语音模块（如果配置启用）。"""
        voice_cfg = self._config.get("voice", {})
        if not voice_cfg.get("enabled", False):
            return
        try:
            from capability.voice.config import VoiceConfig
            from capability.voice.runtime import VoiceRuntimeImpl
            from capability.voice.tts.cosyvoice_client import create_cosyvoice_client

            cfg = VoiceConfig.from_dict(self._config)

            # 创建 TTS 客户端（可选，API key 缺失时跳过）
            tts_client = create_cosyvoice_client(self._config)

            # 包装 LLM 调用：cleanup 用轻量模型，签名 (prompt) -> str
            # 模型在调用时延迟解析，避免 _side_manager 未初始化时拿到默认值
            async def _cleanup_llm(prompt: str) -> str:
                model = self._side_manager.get_side_model() if self._side_manager else "ali/qwen3.6-flash"
                resp = await self._llm_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                )
                return resp.content

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
        """语音输入回调 — 将文本注入 REPL 循环。

        注意：此方法必须在 asyncio event loop 线程中调用。
        如果从音频 I/O 工作线程调用，应使用 loop.call_soon_threadsafe()。
        """
        # 用 VoiceDisplay 显示最终转录结果
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

    def _handle_voice_timing(self, event) -> None:
        """Voice timing hook — 更新 VoiceDisplay 的耗时显示。"""
        if self._voice_display:
            step = event.data.get("step", "")
            ms = event.data.get("ms", 0)
            self._voice_display.update_timing(step, ms)

    def _handle_voice_tts(self, event) -> None:
        """TTS 成功回调 — 输出简短诊断信息。"""
        backend = event.data.get("backend", "unknown")
        chunks = event.data.get("chunks", 0)
        bytes_ = event.data.get("bytes", 0)
        self._console.print(
            f"[dim]TTS ok: backend={backend}, chunks={chunks}, bytes={bytes_}[/]"
        )

    def _handle_voice_tts_error(self, event) -> None:
        """TTS 错误回调 — 输出可见错误。"""
        error = event.data.get("error", "unknown")
        backend = event.data.get("backend", "unknown")
        self._console.print(
            f"[yellow]TTS error: {error} (backend={backend})[/]"
        )

    def _handle_voice_tts_queue(self, event) -> None:
        source = event.data.get("source", "unknown")
        text = event.data.get("text", "")
        self._console.print(
            f"[dim]TTS queue: source={source}, text='{text}'[/]"
        )

    def _handle_voice_tts_skip(self, event) -> None:
        source = event.data.get("source", "unknown")
        text = event.data.get("text", "")
        self._console.print(
            f"[dim]TTS skip: source={source}, text='{text}'[/]"
        )

    def _register_commands(self) -> None:
        """注册所有内置命令和 Skill 到 CommandRegistry。"""
        from capability.command.builtin.session import (
            QuitCommand, ClearCommand, HistoryCommand, ResumeCommand,
        )
        from capability.command.builtin.info import (
            HelpCommand, ModelCommand, SoulCommand, UserCommand, LogCommand,
        )
        from capability.command.skill import SkillCommand
        from capability.command.builtin.voice import VoiceCommand

        # 系统命令
        self._command_registry.register(QuitCommand())
        self._command_registry.register(ClearCommand())
        self._command_registry.register(HistoryCommand())
        self._command_registry.register(ResumeCommand())
        self._command_registry.register(ModelCommand(self._config))
        self._command_registry.register(SoulCommand())
        self._command_registry.register(UserCommand())
        self._command_registry.register(LogCommand())
        # HelpCommand 需要引用 registry
        self._command_registry.register(HelpCommand(self._command_registry))
        # /voice 命令
        self._command_registry.register(VoiceCommand(voice_runtime=self._voice))

        # 内置 Skill
        builtin_skills_dir = Path(__file__).parent.parent / "capability" / "command" / "builtin" / "skills"
        if builtin_skills_dir.is_dir():
            for entry in sorted(builtin_skills_dir.iterdir()):
                skill_file = entry / "SKILL.md"
                if entry.is_dir() and skill_file.is_file():
                    try:
                        self._command_registry.register(SkillCommand(entry))
                    except Exception:
                        pass

    def _register_skill_tool(self) -> None:
        """注册 SkillTool，让 LLM 能通过 function calling 调用 Skill。"""
        self._tool_runner.register(SkillTool(
            registry=self._command_registry,
            data_dir=self._data_dir,
            config=self._config,
            memory=self._memory,
            llm_client=self._llm_client,
        ))

    def _build_orchestrator(self):
        """Build the orchestrator engine based on config."""
        engine_name = self._config.get("engine", "state_machine")
        if engine_name == "langgraph":
            try:
                from orchestrator.langgraph_engine import LangGraphOrchestrator
                return LangGraphOrchestrator()
            except ModuleNotFoundError:
                print("Warning: langgraph not installed, falling back to state_machine engine")
        return StateMachineOrchestrator()

    @staticmethod
    def _build_dynamic_context() -> str:
        """构建动态上下文 — 日期、平台等运行时信息。"""
        import platform
        from datetime import datetime, timezone

        now_utc = datetime.now(timezone.utc)
        now_local = datetime.now().astimezone()
        utc_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
        local_str = now_local.strftime("%Y-%m-%d %H:%M %Z")
        parts = [
            f"Current date/time: {local_str} ({utc_str})",
            f"Platform: {platform.system()} {platform.release()}",
            f"Working directory: {Path.cwd()}",
        ]
        return "\n".join(parts)
