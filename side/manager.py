"""SideTaskManager — 加载、调度、执行 side tasks。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from side.base import SideTask, SideTaskContext
from side.tasks._util import _short_error

logger = logging.getLogger(__name__)



class SideTaskManager:
    """管理所有 side tasks 的生命周期。

    设计原则：
    - 完全可选：没有 manager 或没有 task，agent 正常运行
    - 每个 task 独立开关
    - 失败不影响主流程（catch all exceptions）
    - 支持 fire-and-forget 模式
    """

    def __init__(self) -> None:
        self._tasks: dict[str, SideTask] = {}
        self._config: dict = {}
        self._side_model: str = ""
        self._llm_client: Any = None
        self._memory: Any = None
        self._user_message_count: int = 0
        # 生命周期回调（可选，供状态栏插件等使用）
        self._on_task_start: Callable[[str], None] | None = None
        self._on_task_end: Callable[[str, str, float], None] | None = None

    def configure(
        self,
        config: dict,
        llm_client: Any,
        memory: Any,
    ) -> None:
        """初始化 manager。在 BrixCLI.__init__() 中调用。"""
        self._config = config
        self._llm_client = llm_client
        self._memory = memory
        self._side_model = config.get("side", {}).get("model", "")

    def register(self, task: SideTask) -> None:
        """注册一个 side task。"""
        self._tasks[task.name] = task

    def _build_context(self, **kwargs: Any) -> SideTaskContext:
        """构建 task 执行上下文。传入原始值，SideTaskContext 内部处理深拷贝+冻结。

        非核心 kwargs（排除 session_messages/user_input/hooks）会注入到
        config["_side_task_args"] 中，供需要额外参数的 task 读取。
        """
        _CORE_KEYS = {"session_messages", "user_input", "hooks"}
        extra = {k: v for k, v in kwargs.items() if k not in _CORE_KEYS}
        config = self._config
        if extra:
            config = {**self._config, "_side_task_args": extra}
        return SideTaskContext(
            llm_client=self._llm_client,
            side_model=self._side_model,
            config=config,
            memory=self._memory,
            session_messages=kwargs.get("session_messages", []),
            user_input=kwargs.get("user_input", ""),
            hooks=kwargs.get("hooks"),
        )

    @staticmethod
    def _check_strict_bool(value: object) -> bool:
        """严格布尔检查：仅接受 bool 类型，非布尔值视为 False 并警告。

        与 SideTask.is_enabled() 策略一致。
        """
        if isinstance(value, bool):
            return value
        logger.warning(
            "side.enabled=%r 不是严格布尔值 (type=%s)，视为 disabled",
            value,
            type(value).__name__,
        )
        return False

    def _is_task_enabled(self, task: SideTask) -> bool:
        """检查 task 是否启用（总开关 + side_model 存在 + 单 task 开关）。"""
        if not self._check_strict_bool(self._config.get("side", {}).get("enabled", False)):
            return False
        if not self._side_model:
            return False
        return task.is_enabled(self._config)

    async def run_task(self, task_name: str, **kwargs: Any) -> Any:
        """执行指定 task。失败返回 None，不影响主流程。"""
        task = self._tasks.get(task_name)
        if not task or not self._is_task_enabled(task):
            return None
        start_time = time.monotonic()
        if self._on_task_start:
            try:
                self._on_task_start(task_name)
            except Exception:
                pass
        try:
            ctx = self._build_context(**kwargs)
            result = await task.execute(ctx)
            if self._on_task_end:
                try:
                    self._on_task_end(task_name, "completed", time.monotonic() - start_time)
                except Exception:
                    pass
            return result
        except Exception as e:
            if self._on_task_end:
                try:
                    self._on_task_end(task_name, "error", time.monotonic() - start_time)
                except Exception:
                    pass
            logger.warning("Side task '%s' failed: %s", task_name, e)
            return None

    def fire_and_forget(self, task_name: str, **kwargs: Any) -> None:
        """异步执行 task，不等待结果。无运行中 event loop 时安全跳过。

        支持 on_result 回调：task 完成且结果非 None 时调用 on_result(result)。
        """
        on_result = kwargs.pop("on_result", None)

        async def _run() -> None:
            result = await self.run_task(task_name, **kwargs)
            if result is not None and on_result is not None:
                try:
                    await on_result(result)
                except Exception as e:
                    logger.warning("fire_and_forget on_result: %s", _short_error(e))

        try:
            asyncio.create_task(_run())
        except RuntimeError:
            _run().close()
            logger.warning("fire_and_forget: 没有运行中的 event loop，跳过 task '%s'", task_name)

    def should_run_session_title(self) -> bool:
        """检查是否应该生成会话标题（第 1、3 条用户消息时触发）。"""
        return self._user_message_count in (1, 3)

    def on_user_message(self) -> None:
        """用户消息计数器递增。"""
        self._user_message_count += 1

    def get_side_model(self) -> str:
        """返回 side 模型 ID。"""
        return self._side_model

    def fire_and_forget_session_summary(self) -> None:
        """fire-and-forget 版本的 generate_session_summary，不阻塞退出。"""
        async def _run() -> None:
            try:
                await self.generate_session_summary()
            except Exception as e:
                logger.warning("session_summary: %s", _short_error(e))

        try:
            asyncio.create_task(_run())
        except RuntimeError:
            logger.warning("fire_and_forget_session_summary: 没有运行中的 event loop")

    async def generate_session_summary(self, session_id: str | None = None) -> str | None:
        """生成会话事件摘要并写入短期记忆。

        供退出路径（/clear、/quit、Ctrl+C、compact、兜底）调用。
        无 session 或 side 层未启用时返回 None。

        Args:
            session_id: 指定 session ID。为 None 时使用当前活跃 session。
        """
        if not self._memory:
            return None
        sid = session_id or getattr(self._memory, "current_session_id", None)
        if not sid:
            return None
        # 临时设置 current_session_id，让 task 能找到正确的 session
        original_id = getattr(self._memory, "current_session_id", None)
        if session_id and original_id != session_id:
            self._memory.current_session_id = session_id
        try:
            messages = self._memory.load_session(sid)
        except (FileNotFoundError, ValueError, AttributeError):
            self._memory.current_session_id = original_id
            return None
        if not messages:
            self._memory.current_session_id = original_id
            return None
        # 消息数阈值检查：user 消息不足时跳过 summary
        min_messages = self._config.get("side", {}).get("tasks", {}).get("session_summary", {}).get("min_messages", 3)
        user_msg_count = sum(1 for m in messages if m.get("role") == "user")
        if user_msg_count < min_messages:
            logger.debug("SessionSummary: 用户消息数 %d < 阈值 %d，跳过", user_msg_count, min_messages)
            self._memory.current_session_id = original_id
            return None
        result = await self.run_task(
            "session_summary",
            session_messages=messages,
            user_input="",
            hooks=None,
        )
        # 恢复原始 current_session_id
        self._memory.current_session_id = original_id
        return result

    async def check_previous_session_summary(self) -> str | None:
        """兜底检查：最近一个 session 是否有摘要，没有则生成。

        在 create_session() 时调用，确保历史 session 不会遗漏摘要。
        current_id 为 None 时（首次启动），检查最近的 session。
        """
        if not self._memory:
            return None
        current_id = getattr(self._memory, "current_session_id", None)
        try:
            sessions = self._memory.list_sessions()
        except Exception:
            return None
        # 找到目标 session：排除当前 session（如果有的话）
        for s in sessions:
            prev_id = s.get("id")
            if not prev_id:
                continue
            if current_id and prev_id == current_id:
                continue
            # 检查是否已有摘要
            short_term = getattr(self._memory, "short_term", None)
            if short_term:
                try:
                    existing = short_term.get_by_session(prev_id)
                    if any(i.get("type") == "event" for i in existing):
                        return None  # 已有摘要，无需生成
                except Exception:
                    pass
            # 生成摘要
            return await self.generate_session_summary(prev_id)
        return None

    @property
    def enabled(self) -> bool:
        """side 层是否启用（严格布尔检查）。"""
        return self._check_strict_bool(self._config.get("side", {}).get("enabled", False))
