"""Interactive REPL for Brix."""

from __future__ import annotations

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
from router.complexity import evaluate_complexity
from router.intent import classify_intent
from router.model_router import select_model


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
        self._register_commands()
        self._register_skill_tool()
        self._orchestrator = self._build_orchestrator()
        self._console = Console(theme=BRIX_THEME)

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
                try:
                    user_input = await session.prompt_async(HTML('<ansicyan><b>❯ </b></ansicyan>'))
                except (EOFError, KeyboardInterrupt):
                    self._memory.save_session()
                    self._console.print("\n[dim]Goodbye.[/]")
                    break

                text = user_input.strip()
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

        intent_model = self._config.get("routing", {}).get("intent_model", "")
        default_model = self._config.get("routing", {}).get("default_model", "")
        intent = await classify_intent(
            user_input, context_messages, self._llm_client,
            intent_model or default_model, hooks=hooks,
        )
        complexity = evaluate_complexity(user_input)
        model = select_model(intent, complexity, self._config)

        hooks.fire("complexity", result=complexity)
        hooks.fire("router", model=model, reason=f"{intent}->{complexity}")
        log.set_model(model)

        context = OrchestratorContext(
            history=list(context_messages),
            tool_runner=self._tool_runner,
            llm_client=self._llm_client,
            model=model,
            hooks=hooks,
        )

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

        self._memory.add_message("user", user_input)
        if not response.startswith("Error"):
            self._memory.add_message("assistant", response)
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

        # Intent stage (LLM call — takes time)
        intent_model = self._config.get("routing", {}).get("intent_model", "")
        default_model = self._config.get("routing", {}).get("default_model", "")
        _intent_model_name = (intent_model or default_model).split("/")[-1]
        indicator.update("Intent", _intent_model_name)
        # 只传最近 6 条非 system 消息，避免 intent 分类加载完整 soul.md
        trimmed = [m for m in context_messages if m.get("role") != "system"][-6:]
        intent = await classify_intent(
            user_input, trimmed, self._llm_client,
            intent_model or default_model, hooks=hooks,
        )
        _tick("intent({})".format(intent))

        # Complexity + Route stages
        indicator.update("Complexity")
        complexity = evaluate_complexity(user_input)
        indicator.update("Route")
        model = select_model(intent, complexity, self._config)
        _tick("route->{}".format(model.split("/")[-1]))

        hooks.fire("complexity", result=complexity)
        hooks.fire("router", model=model, reason="{}->{}".format(intent, complexity))
        log.set_model(model)

        context = OrchestratorContext(
            history=list(context_messages),
            tool_runner=self._tool_runner,
            llm_client=self._llm_client,
            model=model,
            hooks=hooks,
        )

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

        # Persist conversation
        self._memory.add_message("user", user_input)
        if not has_error:
            self._memory.add_message("assistant", response)
        self._memory.save_session()
        hooks.fire("persist", saved=2 if not has_error else 1)

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

    def _register_commands(self) -> None:
        """注册所有内置命令和 Skill 到 CommandRegistry。"""
        from capability.command.builtin.session import (
            QuitCommand, ClearCommand, HistoryCommand, ResumeCommand,
        )
        from capability.command.builtin.info import (
            HelpCommand, ModelCommand, SoulCommand, UserCommand, LogCommand,
        )
        from capability.command.skill import SkillCommand

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
