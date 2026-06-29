"""BrixServerApp — 无头核心，等价于去掉所有 UI + voice 的 BrixCLI。"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from capability.runner import ToolRunner
from capability.command.base import CommandContext, CommandResultType
from capability.command.registry import CommandRegistry
from capability.tools.bash import BashTool
from capability.tools.calculator import CalculatorTool
from capability.tools.file_edit import FileEditTool
from capability.tools.file_read import FileReadTool
from capability.tools.file_write import FileWriteTool
from capability.tools.skill_tool import SkillTool
from capability.tools.weather import WeatherTool
from capability.tools.memory_search import MemorySearchTool
from capability.tools.save_memory import SaveMemoryTool
from memory.long_term import LongTermMemory
from memory.searcher import KeywordMemorySearcher
from memory.short_term import ShortTermMemory
from config.loader import load_config
from log.flow import FlowLog
from log.writer import flush_log
from infra.llm_client import LLMClient
from memory import MemoryProvider, create_memory_provider
from orchestrator.engine import OrchestratorContext
from orchestrator.state_machine import StateMachineOrchestrator
from side.manager import SideTaskManager
from side.tasks import ALL_TASKS
from hooks.registry import HookRegistry
from protocol.types import ServerEvent
from server.session_handler import SessionContext, SessionHandler

logger = logging.getLogger(__name__)


class BrixServerApp:
    """无头核心 — 等价于去掉所有 UI + voice 的 BrixCLI。

    Server 只保留逻辑，不拥有任何 IO 设备或 UI 组件。
    """

    def __init__(self, config: dict) -> None:
        self._config = config
        self._data_dir = Path(config.get("memory", {}).get("data_dir", "memory/data"))
        max_tokens = config.get("memory", {}).get("max_context_tokens", 8000)

        # 核心组件
        self._llm_client = LLMClient(config)
        self._tool_runner = ToolRunner()
        self._command_registry = CommandRegistry()
        self._orchestrator = self._build_orchestrator(config)

        # SideTaskManager（全局共享，memory 通过 SessionContext 传入）
        self._side_manager = SideTaskManager()
        self._side_manager.configure(
            config=config,
            llm_client=self._llm_client,
            memory=None,  # 不绑定全局 memory
        )
        for task in ALL_TASKS:
            self._side_manager.register(task)

        # Session 管理
        self._session_handler = SessionHandler(
            data_dir=self._data_dir,
            max_context_tokens=max_tokens,
        )

        # 注册工具、命令、Skill
        self._register_tools()
        self._register_commands()
        self._register_skill_tool()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_session_context(self, client_id: str) -> SessionContext | None:
        """获取指定连接的 SessionContext。"""
        return self._session_handler.get_context(client_id)

    def create_session_context(self, client_id: str) -> SessionContext:
        """为新连接创建独立的 SessionContext。"""
        return self._session_handler.create_context(client_id)

    def release_session_context(self, client_id: str) -> None:
        """客户端断开时释放 session 资源。"""
        self._session_handler.release_context(client_id)

    async def handle_chat(
        self, content: str, ctx: SessionContext
    ) -> AsyncGenerator[dict[str, Any], None]:
        """处理一条聊天消息，yield 流式事件序列。

        核心逻辑从 BrixCLI._process_streaming() 迁移而来，
        去掉所有 Rich Console / StreamRenderer / ToolDisplay 调用。
        """
        # 兜底检查：即将创建新 session 时，检查上一个 session 是否有摘要
        if ctx.memory.current_session_id is None and self._side_manager:
            await self._side_manager.check_previous_session_summary()

        log = FlowLog(content)
        hooks = HookRegistry()
        hooks.bind_log(log)

        # Memory stage — build system prompt and context via MemoryProvider
        dynamic_ctx = self._build_dynamic_context()
        system_prompt = ctx.memory.build_system_prompt(dynamic_context=dynamic_ctx)
        # 注入 Skill 列表到 system prompt
        skill_listing = self._command_registry.get_skill_listing_text()
        if skill_listing:
            system_prompt = system_prompt + "\n\n" + skill_listing
        context_messages = ctx.memory.get_context_messages(system_prompt)
        hooks.fire(
            "memory",
            msgs=len(context_messages),
            chars=sum(len(m.get("content", "")) for m in context_messages),
        )

        # Dream 蒸馏（fire-and-forget，不影响主流程）
        if self._side_manager and self._side_manager.enabled:
            self._side_manager.fire_and_forget(
                "dream",
                session_messages=context_messages,
                user_input=content,
                hooks=hooks,
            )

        # Side 层：历史搜索（如果触发）
        if self._side_manager and self._side_manager.enabled:
            search_results = await self._side_manager.run_task(
                "history_search",
                session_messages=context_messages,
                user_input=content,
                hooks=hooks,
            )
            if search_results:
                search_summary = "\n".join(
                    f"- {s.get('title', '无标题')}: {s.get('summary', '')[:100]}"
                    for s in search_results
                )
                context_messages.append(
                    {
                        "role": "user",
                        "content": f"[系统] 以下是你之前的对话，可能与当前问题相关：\n{search_summary}",
                    }
                )

        # 直接使用 config 中的主模型
        model = self._resolve_model()
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

        # 流式处理
        has_error = False
        tool_input_cache: dict[str, dict] = {}

        try:
            async for event in self._orchestrator.run_stream(content, context):
                event_type = event.get("type", "")

                # 转换为 ServerEvent 格式
                yield event

                # fire-and-forget 工具摘要
                if event_type == "tool_result" and self._side_manager and self._side_manager.enabled:
                    tc_id = event.get("id", "")
                    tc_input = tool_input_cache.pop(tc_id, {})
                    self._side_manager.fire_and_forget(
                        "tool_summary",
                        session_messages=context_messages,
                        user_input=content,
                        hooks=hooks,
                        tool_name=event.get("name", ""),
                        tool_input=tc_input,
                        tool_result=event.get("result", ""),
                    )
                elif event_type == "tool_call":
                    tc_id = event.get("id", "")
                    if tc_id:
                        tool_input_cache[tc_id] = event.get("input", {})

        except Exception as exc:
            has_error = True
            log.set_error(str(exc))
            yield {"type": "error", "message": str(exc)}

        # Flush any remaining content
        yield {"type": "stream_end"}

        response = "".join(
            msg.get("content", "")
            for msg in context.history[original_history_count:]
            if msg.get("role") == "assistant"
        )

        if response.startswith("Error"):
            has_error = True
            log.set_error(response)

        # 持久化本轮新增的完整消息
        if not has_error:
            new_messages = context.history[original_history_count:]
            for msg in new_messages:
                if msg.get("role") != "system":
                    ctx.memory.add_full_message(msg)
        ctx.memory.save_session()
        hooks.fire("persist", saved=2 if not has_error else 1)

        # 会话标题生成（第 1、3 条消息时触发）
        if (
            self._side_manager
            and self._side_manager.enabled
            and self._side_manager.should_run_session_title()
        ):

            async def _save_title(title: str) -> None:
                sid = ctx.memory.current_session_id
                if sid and title:
                    ctx.memory.update_session_title(sid, title)

            self._side_manager.fire_and_forget(
                "session_title",
                session_messages=context_messages,
                user_input=content,
                hooks=hooks,
                on_result=_save_title,
            )

        try:
            flush_log(log)
        except Exception:
            pass

    async def handle_command(
        self, command: str, args: str, ctx: SessionContext
    ) -> dict[str, Any]:
        """执行 slash 命令，返回结构化结果。

        与 BrixCLI._handle_command() 等价，但：
        - 不调用 print() / sys.exit()
        - 不调用 console.print()
        - 返回结构化数据
        """
        # 向后兼容：/exit 映射到 /quit
        if command == "exit":
            command = "quit"

        cmd = self._command_registry.get(command)
        if not cmd:
            return {"type": "error", "message": f"Unknown command: /{command}"}

        cmd_ctx = CommandContext(
            session_id=ctx.memory.current_session_id or "",
            data_dir=str(self._data_dir),
            console=None,  # Server 端没有 console
            config=self._config,
            memory=ctx.memory,
            llm_client=self._llm_client,
        )

        # /clear 和 /quit 退出前保存会话摘要
        if command in ("clear", "quit"):
            if self._side_manager and self._side_manager.enabled:
                try:
                    self._side_manager.fire_and_forget_session_summary()
                except Exception:
                    pass

        # /quit 直接返回 QUIT 结果，不调用 cmd.execute()
        # 因为 QuitCommand 调用 sys.exit(0) 会抛 SystemExit 导致 Server 崩溃
        if command == "quit":
            ctx.memory.save_session()
            return {"type": "command_result", "command": "quit", "data": {"action": "quit"}}

        # /resume 直接返回 sessions 列表，供 TUI 渲染交互式选择器
        if command == "resume":
            sessions = ctx.memory.list_sessions()
            if not sessions:
                return {
                    "type": "command_result",
                    "command": "resume",
                    "data": {"sessions": [], "output": "No sessions yet."},
                }
            # 如果有 args，尝试直接匹配
            if args.strip():
                prefix = args.strip()
                matches = [s for s in sessions if s["id"].startswith(prefix)]
                if len(matches) == 1:
                    msgs = ctx.memory.resume_session(matches[0]["id"])
                    return {
                        "type": "command_result",
                        "command": "resume",
                        "data": {
                            "resumed_session_id": matches[0]["id"],
                            "messages": msgs,
                        },
                    }
            # 返回 sessions 列表供 TUI 选择
            return {
                "type": "command_result",
                "command": "resume",
                "data": {"sessions": sessions},
            }

        # 捕获 stdout（命令可能用 print() 输出）
        import io
        import contextlib
        stdout_capture = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_capture):
                result = await cmd.execute(args, cmd_ctx)
        except Exception as exc:
            return {"type": "error", "message": str(exc)}

        captured_output = stdout_capture.getvalue()

        if result.type == CommandResultType.QUIT:
            return {"type": "command_result", "command": command, "data": {"action": "quit"}}
        elif result.type == CommandResultType.CLEAR:
            return {"type": "command_result", "command": command, "data": {"action": "clear"}}
        elif result.type == CommandResultType.PROMPT:
            # PROMPT 类型需要客户端处理
            return {
                "type": "command_result",
                "command": command,
                "data": {"action": "prompt", "text": result.prompt_text},
            }

        # NONE 类型：返回捕获的 stdout 输出
        return {
            "type": "command_result",
            "command": command,
            "data": {"output": captured_output} if captured_output else {},
        }

    async def shutdown(self) -> None:
        """优雅关闭：保存所有 session、关闭 LLM client、清理 side tasks。"""
        logger.info("Shutting down server...")
        # 保存所有活跃 session
        for ctx in self._session_handler.get_all_contexts():
            try:
                ctx.memory.save_session()
            except Exception:
                logger.exception("Failed to save session for client %s", ctx.client_id)
        # 关闭 LLM client
        await self._llm_client.close()
        logger.info("Server shutdown complete")

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _resolve_model(self) -> str:
        """解析主模型：default_model → fallback_model → 空字符串。"""
        routing = self._config.get("routing", {})
        return routing.get("default_model", "") or routing.get("fallback_model", "")

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

    def _build_orchestrator(self, config: dict) -> StateMachineOrchestrator:
        """Build the orchestrator engine based on config."""
        engine_name = config.get("engine", "state_machine")
        if engine_name == "langgraph":
            try:
                from orchestrator.langgraph_engine import LangGraphOrchestrator
                return LangGraphOrchestrator()
            except ModuleNotFoundError:
                logger.warning("langgraph not installed, falling back to state_machine engine")
        return StateMachineOrchestrator()

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_tools(self) -> None:
        """Register all built-in tools."""
        data_root = self._data_dir
        self._tool_runner.register(BashTool())
        self._tool_runner.register(CalculatorTool())
        self._tool_runner.register(WeatherTool())
        self._tool_runner.register(FileReadTool())
        self._tool_runner.register(FileWriteTool(allowed_root=data_root))
        self._tool_runner.register(FileEditTool(allowed_root=data_root))
        # 记忆搜索工具（per-connection memory）
        self._tool_runner.register(MemorySearchTool(server_app=self))
        # 主模型主动写入记忆（per-connection memory）
        self._tool_runner.register(SaveMemoryTool(server_app=self))

    def _register_commands(self) -> None:
        """注册所有内置命令和 Skill 到 CommandRegistry。"""
        from capability.command.builtin.session import (
            QuitCommand,
            ClearCommand,
            HistoryCommand,
            ResumeCommand,
        )
        from capability.command.builtin.info import (
            HelpCommand,
            ModelCommand,
            SoulCommand,
            UserCommand,
            LogCommand,
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
        builtin_skills_dir = (
            Path(__file__).parent.parent / "capability" / "command" / "builtin" / "skills"
        )
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
        self._tool_runner.register(
            SkillTool(
                registry=self._command_registry,
                data_dir=str(self._data_dir),
                config=self._config,
                memory=None,  # 不绑定全局 memory
                llm_client=self._llm_client,
            )
        )
