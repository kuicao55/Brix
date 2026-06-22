"""ConversationRunner — 业务编排层。

管理一次对话的完整生命周期，不包含任何 UI 渲染逻辑。
通过 UIAdapter Protocol 通知 UI 层进行渲染。

从 cli/app.py 的 _process_streaming() 中提取的纯业务逻辑。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from capability.command.base import CommandContext, CommandResult, CommandResultType
from capability.command.registry import CommandRegistry
from hooks.registry import HookRegistry
from log.flow import FlowLog
from log.writer import flush_log
from memory import MemoryProvider
from infra.llm_client import LLMClient
from orchestrator.engine import OrchestratorContext, OrchestratorEngine
from orchestrator.state_machine import StateMachineOrchestrator
from side.manager import SideTaskManager


class ConversationRunner:
    """业务编排层 — 管理一次对话的完整生命周期。

    不包含任何 UI 渲染逻辑，通过 UIAdapter 通知 UI 层。
    """

    def __init__(
        self,
        memory: MemoryProvider,
        llm_client: LLMClient,
        tool_runner: Any,
        orchestrator: OrchestratorEngine,
        side_manager: SideTaskManager | None,
        command_registry: CommandRegistry,
        config: dict,
    ) -> None:
        self._memory = memory
        self._llm_client = llm_client
        self._tool_runner = tool_runner
        self._orchestrator = orchestrator
        self._side_manager = side_manager
        self._command_registry = command_registry
        self._config = config

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_streaming(self, user_input: str, ui: Any) -> str:
        """处理一次用户输入，返回完整回复文本。

        Args:
            user_input: 用户输入文本
            ui: UIAdapter 实例，用于通知 UI 渲染

        Returns:
            完整的回复文本
        """
        # 兜底检查：即将创建新 session 时，检查上一个 session 是否有摘要
        if self._memory.current_session_id is None and self._side_manager:
            await self._side_manager.check_previous_session_summary()

        _t_start = time.monotonic()
        _timing: list[tuple[str, int]] = []

        def _tick(label: str):
            _timing.append((label, int((time.monotonic() - _t_start) * 1000)))

        log = FlowLog(user_input)
        hooks = HookRegistry()
        hooks.bind_log(log)

        # Memory stage
        ui.update_stage("Memory")
        dynamic_ctx = self._build_dynamic_context()
        system_prompt = self._memory.build_system_prompt(dynamic_context=dynamic_ctx)
        # 注入 Skill 列表到 system prompt
        skill_listing = self._command_registry.get_skill_listing_text()
        if skill_listing:
            system_prompt = system_prompt + "\n\n" + skill_listing
        context_messages = self._memory.get_context_messages(system_prompt)
        hooks.fire(
            "memory",
            msgs=len(context_messages),
            chars=sum(len(m.get("content", "")) for m in context_messages),
        )
        _tick("memory")

        # Dream 蒸馏（fire-and-forget）
        if self._side_manager and self._side_manager.enabled:
            self._side_manager.fire_and_forget(
                "dream",
                session_messages=context_messages,
                user_input=user_input,
                hooks=hooks,
            )

        # Side 层：历史搜索
        if self._side_manager and self._side_manager.enabled:
            ui.update_stage("Side", "history_search")
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

        # 模型解析
        model = self._resolve_model()
        hooks.fire("router", model=model, reason="direct_config")
        log.set_model(model)

        # 用户消息计数
        if self._side_manager:
            self._side_manager.on_user_message()

        context = OrchestratorContext(
            history=list(context_messages),
            tool_runner=self._tool_runner,
            llm_client=self._llm_client,
            model=model,
            hooks=hooks,
        )

        original_history_count = len(context.history)

        # Planning stage
        ui.update_stage("Planning", model.split("/")[-1])

        content_parts: list[str] = []
        has_error = False
        _tool_input_cache: dict[str, dict] = {}

        try:
            async for event in self._orchestrator.run_stream(user_input, context):
                event_type = event.get("type", "")

                if event_type == "thinking_delta":
                    text = event.get("text", "")
                    if text:
                        ui.push_thinking_delta(text)

                elif event_type == "text_delta":
                    text = event.get("text", "")
                    if text:
                        # thinking → streaming 切换由 UIAdapter 内部处理
                        ui.push_text_delta(text)
                        content_parts.append(text)

                elif event_type == "tool_call":
                    ui.stop_stage()
                    ui.flush_thinking()
                    ui.flush_streaming()
                    tool_name = event.get("name", "unknown")
                    _tc_id = event.get("id", "")
                    if _tc_id:
                        _tool_input_cache[_tc_id] = event.get("input", {})
                    ui.show_tool_start(tool_name, event.get("input", {}))

                elif event_type == "tool_result":
                    tool_name = event.get("name", "unknown")
                    elapsed_ms = event.get("ms", 0)
                    is_err = event.get("is_error", False)
                    ui.show_tool_result(
                        tool_name,
                        event.get("result", ""),
                        elapsed_ms,
                        is_error=is_err,
                    )

                # fire-and-forget 工具摘要
                if (
                    event_type == "tool_result"
                    and self._side_manager
                    and self._side_manager.enabled
                ):
                    _tc_id = event.get("id", "")
                    _tc_input = _tool_input_cache.pop(_tc_id, {})
                    self._side_manager.fire_and_forget(
                        "tool_summary",
                        session_messages=context_messages,
                        user_input=user_input,
                        hooks=hooks,
                        tool_name=tool_name,
                        tool_input=_tc_input,
                        tool_result=event.get("result", ""),
                    )

        except Exception as exc:
            has_error = True
            ui.flush_thinking()
            ui.flush_streaming()
            log.set_error(str(exc))
            err_text = str(exc).split("\n")[0].strip()
            if len(err_text) > 200:
                err_text = err_text[:199] + "…"
            ui.print(f"Error: {err_text}", style="error")

        finally:
            ui.stop_stage()

        # Flush remaining content
        ui.flush_thinking()
        ui.flush_streaming()
        _tick("stream_end")

        response = "".join(content_parts)

        # TTS 桥接（如果 voice 模块启用）
        # 注意：voice 的 feed_response_text 由调用方（BrixCLI）处理，
        # 因为 voice runtime 的生命周期由 BrixCLI 管理

        # Write timing data
        try:
            with open("/tmp/brix_timing.log", "a") as _f:
                _f.write("input: {}\n".format(user_input[:60]))
                for label, ms in _timing:
                    prev = 0
                    for _, p in _timing:
                        if _ == label:
                            break
                        prev = p
                    _f.write("  {:>12}: {:>5}ms  (+{}ms)\n".format(label, ms, ms - prev))
                _f.write("\n")
        except Exception:
            pass

        if response.startswith("Error"):
            has_error = True
            log.set_error(response)

        # 持久化本轮新增的完整消息
        if not has_error:
            new_messages = context.history[original_history_count:]
            for msg in new_messages:
                if msg.get("role") != "system":
                    self._memory.add_full_message(msg)
        self._memory.save_session()
        hooks.fire("persist", saved=2 if not has_error else 1)

        # 会话标题生成
        if (
            self._side_manager
            and self._side_manager.enabled
            and self._side_manager.should_run_session_title()
        ):

            async def _save_title(title: str) -> None:
                sid = getattr(self._memory, "current_session_id", None)
                if sid and title:
                    self._memory.update_session_title(sid, title)

            self._side_manager.fire_and_forget(
                "session_title",
                session_messages=context_messages,
                user_input=user_input,
                hooks=hooks,
                on_result=_save_title,
            )

        try:
            flush_log(log)
        except Exception:
            pass

        return response

    async def handle_command(self, text: str, ui: Any) -> CommandResult:
        """处理 slash 命令。

        Args:
            text: 完整的命令文本（含 / 前缀）
            ui: UIAdapter 实例

        Returns:
            CommandResult，调用方根据 type 决定后续行为
        """
        parts = text.split()
        cmd_name = parts[0].lower().lstrip("/")
        args = " ".join(parts[1:]) if len(parts) > 1 else ""

        # 向后兼容：/exit 映射到 /quit
        if cmd_name == "exit":
            cmd_name = "quit"

        command = self._command_registry.get(cmd_name)
        if not command:
            ui.print(f"Unknown command: /{cmd_name}", style="error")
            return CommandResult(type=CommandResultType.NONE)

        ctx = CommandContext(
            session_id="",
            data_dir=str(self._memory._data_dir) if hasattr(self._memory, "_data_dir") else "",
            ui=ui,
            config=self._config,
            memory=self._memory,
            llm_client=self._llm_client,
        )

        # /clear 和 /quit 退出前保存会话摘要
        if cmd_name in ("clear", "quit") and self._side_manager:
            try:
                self._side_manager.fire_and_forget_session_summary()
            except Exception:
                pass

        result = await command.execute(args, ctx)

        if result.type == CommandResultType.PROMPT:
            ui.print("")  # 空行间隔
            await self.process_streaming(result.prompt_text, ui)

        return result
