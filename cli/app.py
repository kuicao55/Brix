"""BrixCLI — Composition root，接线所有模块并启动应用。

职责：
1. 初始化核心模块（memory、llm、tools、commands、orchestrator、side tasks）
2. 创建 UI 适配器（TuiAdapter）
3. 创建业务编排器（ConversationRunner）
4. 运行 REPL 循环

不包含任何渲染逻辑或业务编排逻辑——这些分别由 TuiAdapter 和 ConversationRunner 处理。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from capability.runner import ToolRunner
from capability.command.base import CommandResultType
from capability.command.registry import CommandRegistry
from capability.tools.bash import BashTool
from capability.tools.calculator import CalculatorTool
from capability.tools.file_edit import FileEditTool
from capability.tools.file_read import FileReadTool
from capability.tools.file_write import FileWriteTool
from capability.tools.skill_tool import SkillTool
from capability.tools.memory_search import MemorySearchTool
from capability.tools.save_memory import SaveMemoryTool
from cli.tui_adapter import TuiAdapter
from cli.theme import BRIX_THEME
from config.loader import load_config
from hooks.registry import HookRegistry
from infra.llm_client import LLMClient
from memory import MemoryProvider, create_memory_provider
from memory.long_term import LongTermMemory
from memory.searcher import KeywordMemorySearcher
from memory.short_term import ShortTermMemory
from orchestrator.engine import OrchestratorContext
from orchestrator.runner import ConversationRunner
from orchestrator.state_machine import StateMachineOrchestrator
from plugins.status_bar.plugin import StatusBarPlugin
from plugins.status_bar.slots import load_enabled_slots
from cli.status_bar import StatusBarRenderer
from side.manager import SideTaskManager
from side.tasks import ALL_TASKS


class BrixCLI:
    """Composition root — 接线所有模块，启动应用。"""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config if config is not None else load_config()
        self._data_dir = self._config.get("memory", {}).get("data_dir", "memory/data")
        max_tokens = self._config.get("memory", {}).get("max_context_tokens", 8000)

        # 核心模块
        self._memory: MemoryProvider = create_memory_provider(
            data_dir=self._data_dir,
            max_context_tokens=max_tokens,
        )
        self._llm_client = LLMClient(self._config)
        self._tool_runner = ToolRunner()
        self._register_tools()
        self._command_registry = CommandRegistry()
        self._orchestrator = self._build_orchestrator()

        # SideTaskManager
        self._side_manager = SideTaskManager()
        self._side_manager.configure(
            config=self._config,
            llm_client=self._llm_client,
            memory=self._memory,
        )
        for task in ALL_TASKS:
            self._side_manager.register(task)

        # 状态栏（可选）
        self._status_bar_renderer: StatusBarRenderer | None = None
        self._status_bar_plugin: StatusBarPlugin | None = None
        self._status_bar_enabled = self._config.get("status_bar", {}).get("enabled", True)
        if self._status_bar_enabled:
            self._status_bar_plugin = StatusBarPlugin(side_model=self._side_manager.get_side_model())
            self._status_bar_renderer = StatusBarRenderer(self._status_bar_plugin)
            for slot in load_enabled_slots(self._config):
                self._status_bar_renderer.add_slot(slot)
            self._side_manager._on_task_start = self._status_bar_plugin.on_task_start
            self._side_manager._on_task_end = self._status_bar_plugin.on_task_end

        # UI 适配器
        self._ui = TuiAdapter(
            console=Console(theme=BRIX_THEME),
            config=self._config,
            command_registry=self._command_registry,
            status_bar_renderer=self._status_bar_renderer,
        )

        # 状态栏变化时重绘
        if self._status_bar_plugin:
            self._status_bar_plugin.set_on_change(self._ui.repaint_status_bar)

        # 语音模块（可选）
        self._voice = None
        self._voice_input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._init_voice()

        # 注册命令和 SkillTool
        self._register_commands()
        self._register_skill_tool()

        # 业务编排器
        self._runner = ConversationRunner(
            memory=self._memory,
            llm_client=self._llm_client,
            tool_runner=self._tool_runner,
            orchestrator=self._orchestrator,
            side_manager=self._side_manager,
            command_registry=self._command_registry,
            config=self._config,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start the REPL loop."""
        self._ui.setup()

        first_turn = True
        try:
            while True:
                if not first_turn:
                    self._ui.print("")
                first_turn = False

                # 并行等待键盘输入和语音输入
                keyboard_task = asyncio.create_task(
                    self._ui.prompt_async(prefix="❯ ")
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
                    self._save_session_summary()
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
                        self._save_session_summary()
                        self._memory.save_session()
                        self._ui.print("Goodbye.", style="muted")
                        break
                else:
                    continue

                text = text.strip()
                if not text:
                    continue

                # Slash commands
                if text.startswith("/"):
                    result = await self._runner.handle_command(text, self._ui)
                    if result.type == CommandResultType.QUIT:
                        break
                    continue

                # Normal message — stream response
                self._ui.print("")  # ❯ 和 ⏺ 之间的间隔
                try:
                    response = await self._runner.process_streaming(text, self._ui)
                    # 状态栏重绘（streaming 结束后恢复）
                    self._ui.repaint_status_bar()
                    # TTS 桥接：完整回复后一次性触发
                    if (self._voice and self._voice.is_running
                            and self._voice.output_enabled and response.strip()):
                        self._ui.print(f"TTS trigger: chars={len(response)}", style="muted")
                        self._voice.feed_response_text(response)
                        self._voice.flush_tts()
                except KeyboardInterrupt:
                    self._save_session_summary()
                    self._memory.save_session()
                    self._ui.print("Goodbye.", style="muted")
                    break
                except Exception as exc:
                    self._ui.print(f"Error: {exc}", style="error")
        finally:
            if self._voice and self._voice.is_running:
                await self._voice.stop()
            await self._llm_client.close()
            self._ui.teardown()

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _save_session_summary(self) -> None:
        """fire-and-forget：不阻塞退出。"""
        if not self._side_manager or not self._side_manager.enabled:
            return
        try:
            self._side_manager.fire_and_forget_session_summary()
        except Exception:
            pass

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

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_tools(self) -> None:
        """Register all built-in tools."""
        data_root = Path(self._data_dir)
        self._tool_runner.register(BashTool())
        self._tool_runner.register(CalculatorTool())
        self._tool_runner.register(FileReadTool())
        self._tool_runner.register(FileWriteTool(allowed_root=data_root))
        self._tool_runner.register(FileEditTool(allowed_root=data_root))
        # 记忆搜索工具
        searcher = KeywordMemorySearcher(
            long_term=LongTermMemory(data_root),
            short_term=ShortTermMemory(data_root),
        )
        self._tool_runner.register(MemorySearchTool(searcher))
        # 主模型主动写入记忆
        if self._memory:
            short_term = getattr(self._memory, "short_term", None)
            if short_term:
                self._tool_runner.register(SaveMemoryTool(short_term, self._memory))

    # ------------------------------------------------------------------
    # Command registration
    # ------------------------------------------------------------------

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
        self._command_registry.register(HelpCommand(self._command_registry))
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

    # ------------------------------------------------------------------
    # Voice initialization
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

            cfg = VoiceConfig.from_dict(self._config)
            tts_client = create_cosyvoice_client(self._config)

            # LLM cleanup 包装
            _CLEANUP_FALLBACK = "ali/qwen3.6-flash"

            async def _cleanup_llm(prompt: str) -> str:
                model = (
                    voice_cfg.get("cleanup_model", "")
                    or (self._side_manager.get_side_model() if self._side_manager else "")
                    or self._config.get("routing", {}).get("default_model", "")
                    or _CLEANUP_FALLBACK
                )
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

            # 语音输入 → 注入 REPL 循环
            self._voice.on_voice_input(self._handle_voice_input)

            # 语音状态/转录 → 委托给 UIAdapter
            self._voice.on_state_change(self._ui.on_voice_state_change)
            self._voice.on_interim_text(self._ui.on_voice_interim_text)

            # voice timing hook → UIAdapter
            self._voice._hooks.register("voice_timing", self._handle_voice_timing)

        except Exception as exc:
            self._ui.print(f"语音模块加载失败: {exc}", style="muted")

    def _handle_voice_input(self, text: str) -> None:
        """语音输入回调 — 将文本注入 REPL 循环。"""
        # 显示最终转录结果
        self._ui.show_voice_final(text, {})
        self._voice_input_queue.put_nowait(text)

    def _handle_voice_timing(self, event: Any) -> None:
        """Voice timing hook — 更新 UIAdapter 的耗时显示。"""
        step = event.data.get("step", "")
        ms = event.data.get("ms", 0)
        self._ui.update_voice_timing(step, ms)
