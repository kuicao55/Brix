"""SideTaskManager — 加载、调度、执行 side tasks。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from side.base import SideTask, SideTaskContext

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
        try:
            ctx = self._build_context(**kwargs)
            return await task.execute(ctx)
        except Exception as e:
            logger.warning("Side task '%s' failed: %s", task_name, e)
            return None

    def fire_and_forget(
        self,
        task_name: str,
        on_result: Callable[[Any], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> None:
        """异步执行 task，不等待结果。无运行中 event loop 时安全跳过。

        Args:
            on_result: 可选回调，task 执行成功且返回非 None 时调用。
        """
        async def _wrapper() -> None:
            result = await self.run_task(task_name, **kwargs)
            if on_result and result is not None:
                try:
                    await on_result(result)
                except Exception:
                    logger.warning(
                        "fire_and_forget on_result 回调失败: task='%s'",
                        task_name,
                        exc_info=True,
                    )

        coro = _wrapper()
        try:
            asyncio.create_task(coro)
        except RuntimeError:
            coro.close()  # 避免 RuntimeWarning: coroutine was never awaited
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

    @property
    def enabled(self) -> bool:
        """side 层是否启用（严格布尔检查）。"""
        return self._check_strict_bool(self._config.get("side", {}).get("enabled", False))
