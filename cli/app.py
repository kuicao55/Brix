"""Interactive REPL for Brix."""

from __future__ import annotations

import sys
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from capability.runner import ToolRunner
from capability.tools.calculator import CalculatorTool
from capability.tools.file_read import FileReadTool
from capability.tools.weather import WeatherTool
from cli.display import format_response
from config.loader import load_config
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
        self._strategy = MemoryStrategy()
        self._llm_client = LLMClient(self._config)
        self._tool_runner = ToolRunner()
        self._register_tools()
        self._orchestrator = StateMachineOrchestrator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start the REPL loop."""
        session: PromptSession[str] = PromptSession(history=InMemoryHistory())
        print("Brix — personal AI agent (type /quit to exit)")

        while True:
            try:
                user_input = await session.prompt_async("you> ")
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break

            text = user_input.strip()
            if not text:
                continue

            # Slash commands
            if text.startswith("/"):
                if self._handle_command(text):
                    continue
                # /quit returns True from _handle_command after printing

            # Normal message — route and run
            try:
                response = await self._process(text)
            except Exception as exc:
                response = f"Error: {exc}"

            print(format_response(response))

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

        print(f"Unknown command: {cmd}")
        return True

    # ------------------------------------------------------------------
    # Core processing pipeline
    # ------------------------------------------------------------------

    async def _process(self, user_input: str) -> str:
        """Classify, route, run orchestrator, and persist."""
        history = self._memory.get_history()
        context_window = self._strategy.get_context_window(history)

        intent = await classify_intent(
            user_input, context_window, self._llm_client,
            self._config.get("routing", {}).get("default_model", ""),
        )
        complexity = evaluate_complexity(user_input)
        model = select_model(intent, complexity, self._config)

        context = OrchestratorContext(
            history=list(context_window),
            tool_runner=self._tool_runner,
            llm_client=self._llm_client,
            model=model,
        )

        response = await self._orchestrator.run(user_input, context)

        # Persist conversation
        if self._strategy.should_save({"role": "user", "content": user_input}):
            self._memory.add_message("user", user_input)
        if self._strategy.should_save({"role": "assistant", "content": response}):
            self._memory.add_message("assistant", response)
        self._memory.save()

        return response

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_tools(self) -> None:
        """Register all built-in tools."""
        self._tool_runner.register(CalculatorTool())
        self._tool_runner.register(WeatherTool())
        self._tool_runner.register(FileReadTool())
