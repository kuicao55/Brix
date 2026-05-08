"""Interactive REPL for Brix."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from prompt_toolkit import HTML, PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console

from capability.runner import ToolRunner
from hooks.registry import HookRegistry
from capability.tools.calculator import CalculatorTool
from capability.tools.file_read import FileReadTool
from capability.tools.weather import WeatherTool
from cli.banner import show_banner
from cli.stage_indicator import StageIndicator
from cli.stream_renderer import StreamRenderer
from cli.theme import BRIX_THEME
from cli.tool_display import ToolDisplay
from config.loader import load_config
from log.flow import FlowLog
from log.writer import flush_log, read_all, read_entry, format_compact_list, format_detail, entry_count
from infra.llm_client import LLMClient
from memory.storage import MemoryStorage
from memory.strategy import MemoryStrategy
from orchestrator.engine import OrchestratorContext
from orchestrator.state_machine import StateMachineOrchestrator
from router.complexity import evaluate_complexity
from router.intent import classify_intent
from router.model_router import select_model


class BrixCLI:
    """REPL interface that wires memory, routing, orchestrator, and tools."""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config if config is not None else load_config()
        self._memory = MemoryStorage()
        max_tokens = self._config.get("memory", {}).get("max_context_tokens", 8000)
        self._strategy = MemoryStrategy(max_tokens=max_tokens)
        self._llm_client = LLMClient(self._config)
        self._tool_runner = ToolRunner()
        self._register_tools()
        self._orchestrator = self._build_orchestrator()
        self._console = Console(theme=BRIX_THEME)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start the REPL loop."""
        session = PromptSession(history=InMemoryHistory())
        default_model = self._config.get("routing", {}).get("default_model", "unknown")
        show_banner(console=self._console, model=default_model, version="0.1.0", cwd=str(Path.cwd()))

        while True:
            try:
                user_input = await session.prompt_async(HTML('<ansicyan><b>  ❯ </b></ansicyan>'))
            except (EOFError, KeyboardInterrupt):
                self._console.print("\n[dim]Goodbye.[/]")
                break

            text = user_input.strip()
            if not text:
                continue

            # Slash commands
            if text.startswith("/"):
                if self._handle_command(text):
                    continue
                # /quit returns True from _handle_command after printing

            # Normal message — stream response
            try:
                await self._process_streaming(text)
            except Exception as exc:
                self._console.print("[red]Error:[/] {}".format(exc))

    # ------------------------------------------------------------------
    # Command handling
    # ------------------------------------------------------------------

    def _handle_command(self, text: str) -> bool:
        """Handle slash commands. Returns True to continue the loop."""
        cmd = text.split()[0].lower()

        if cmd == "/quit" or cmd == "/exit":
            print("Goodbye.")
            sys.exit(0)

        if cmd == "/clear":
            self._memory.clear()
            self._memory.save()
            print("History cleared.\n")
            return True

        if cmd == "/model":
            default_model = self._config.get("routing", {}).get("default_model", "unknown")
            print(f"Current model: {default_model}")
            return True

        if cmd == "/history":
            history = self._memory.get_history()
            if not history:
                print("No history yet.")
            else:
                for msg in history:
                    role = msg.get("role", "?")
                    content = msg.get("content", "")
                    print(f"  [{role}] {content[:80]}")
            return True

        if cmd == "/log":
            parts = text.split()
            total = entry_count()
            if total == 0:
                print("No logs yet.")
                return True

            # /log <number> — show detail for that entry
            if len(parts) > 1 and parts[1].isdigit():
                idx = int(parts[1])
                entry = read_entry(idx)
                if entry is None:
                    print(f"Log #{idx} not found. (1-{total})")
                else:
                    print(format_detail(entry))
                return True

            # /log — show compact list of last 20, newest first
            entries = read_all()[-20:][::-1]
            print(f"Recent logs (newest first, 1-{total}):\n")
            print(format_compact_list(entries, 1))
            print(f"\nUse /log <number> to view details")
            return True

        print(f"Unknown command: {cmd}")
        return True

    # ------------------------------------------------------------------
    # Core processing pipeline
    # ------------------------------------------------------------------

    async def _process(self, user_input: str) -> str:
        """Classify, route, run orchestrator, and persist."""
        log = FlowLog(user_input)
        hooks = HookRegistry()
        hooks.bind_log(log)

        history = self._memory.get_history()
        context_window = self._strategy.get_context_window(history)
        hooks.fire("memory", msgs=len(history),
                 window=len(context_window),
                 chars=sum(len(m.get("content", "")) for m in context_window),
                 context_window=[{"role": m.get("role"), "content": m.get("content", "")}
                                 for m in context_window])

        default_model = self._config.get("routing", {}).get("default_model", "")
        intent = await classify_intent(
            user_input, context_window, self._llm_client,
            default_model, hooks=hooks,
        )
        complexity = evaluate_complexity(user_input)
        model = select_model(intent, complexity, self._config)

        hooks.fire("complexity", result=complexity)
        hooks.fire("router", model=model, reason=f"{intent}->{complexity}")
        log.set_model(model)

        context = OrchestratorContext(
            history=list(context_window),
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

        # Check for orchestrator-internal errors (returned as strings)
        if response.startswith("Error"):
            log.set_error(response)

        # Persist conversation (skip error responses to avoid polluting context)
        saved_count = 0
        is_error = response.startswith("Error")
        if self._strategy.should_save({"role": "user", "content": user_input}):
            self._memory.add_message("user", user_input)
            saved_count += 1
        if not is_error and self._strategy.should_save({"role": "assistant", "content": response}):
            self._memory.add_message("assistant", response)
            saved_count += 1
        self._memory.save()
        hooks.fire("persist", saved=saved_count)

        try:
            flush_log(log)
        except Exception:
            pass

        return response

    async def _process_streaming(self, user_input: str) -> None:
        """Stream orchestrator output with unified spinner and markdown rendering."""
        indicator = StageIndicator(self._console)

        log = FlowLog(user_input)
        hooks = HookRegistry()
        hooks.bind_log(log)

        # Memory stage
        history = self._memory.get_history()
        context_window = self._strategy.get_context_window(history)
        hooks.fire("memory", msgs=len(history),
                   window=len(context_window),
                   chars=sum(len(m.get("content", "")) for m in context_window),
                   context_window=[{"role": m.get("role"), "content": m.get("content", "")}
                                   for m in context_window])

        # Intent stage
        default_model = self._config.get("routing", {}).get("default_model", "")
        intent = await classify_intent(
            user_input, context_window, self._llm_client,
            default_model, hooks=hooks,
        )
        indicator.update("Intent")

        # Complexity + Route stages
        complexity = evaluate_complexity(user_input)
        model = select_model(intent, complexity, self._config)
        indicator.update("Route")

        hooks.fire("complexity", result=complexity)
        hooks.fire("router", model=model, reason="{}->{}".format(intent, complexity))
        log.set_model(model)

        context = OrchestratorContext(
            history=list(context_window),
            tool_runner=self._tool_runner,
            llm_client=self._llm_client,
            model=model,
            hooks=hooks,
        )

        # Planning stage
        indicator.update("Planning")

        renderer = None
        content_parts = []
        has_error = False
        tool_display = ToolDisplay(self._console)

        try:
            async for event in self._orchestrator.run_stream(user_input, context):
                event_type = event.get("type", "")

                if event_type == "text_delta":
                    text = event.get("text", "")
                    if text:
                        if renderer is None:
                            indicator.finish()
                            renderer = StreamRenderer(self._console)
                            renderer.start()
                        renderer.push_delta(text)
                        content_parts.append(text)

                elif event_type == "tool_call":
                    indicator.finish()
                    if renderer is not None:
                        renderer.flush()
                        renderer = None
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

        except Exception as exc:
            has_error = True
            if renderer is not None:
                renderer.flush()
                renderer = None
            log.set_error(str(exc))
            self._console.print("[red]Error:[/] {}".format(exc))

        finally:
            indicator.finish()

        # Flush any remaining content
        if renderer is not None:
            renderer.flush()

        response = "".join(content_parts)

        if response.startswith("Error"):
            has_error = True
            log.set_error(response)

        # Persist conversation
        saved_count = 0
        if self._strategy.should_save({"role": "user", "content": user_input}):
            self._memory.add_message("user", user_input)
            saved_count += 1
        if not has_error and self._strategy.should_save({"role": "assistant", "content": response}):
            self._memory.add_message("assistant", response)
            saved_count += 1
        self._memory.save()
        hooks.fire("persist", saved=saved_count)

        try:
            flush_log(log)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_tools(self) -> None:
        """Register all built-in tools."""
        self._tool_runner.register(CalculatorTool())
        self._tool_runner.register(WeatherTool())
        self._tool_runner.register(FileReadTool())

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
