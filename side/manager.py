"""SideTaskManager — 加载、调度、执行 side tasks。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL = 5


def _sanitize_interval(raw: object) -> int:
    """校验并清洗 interval 配置值。

    规则：
    - 布尔值直接拒绝（bool 是 int 子类，True 会变成 1，导致每轮触发）
    - 尝试 int(raw)，失败则回退默认值
    - 结果 <= 0 则回退默认值
    """
    if isinstance(raw, bool):
        logger.warning("pref_detection interval=%r 是布尔值，使用默认值 %d", raw, _DEFAULT_INTERVAL)
        return _DEFAULT_INTERVAL
    try:
        interval = int(raw)
    except (TypeError, ValueError):
        logger.warning("pref_detection interval=%r 无法转换为 int，使用默认值 %d", raw, _DEFAULT_INTERVAL)
        return _DEFAULT_INTERVAL
    if interval <= 0:
        logger.warning("pref_detection interval=%r 非正整数，使用默认值 %d", raw, _DEFAULT_INTERVAL)
        return _DEFAULT_INTERVAL
    return interval


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
        """构建 task 执行上下文。传入原始值，SideTaskContext 内部处理深拷贝+冻结。"""
        return SideTaskContext(
            llm_client=self._llm_client,
            side_model=self._side_model,
            config=self._config,
            memory=self._memory,
            session_messages=kwargs.get("session_messages", []),
            user_input=kwargs.get("user_input", ""),
            hooks=kwargs.get("hooks"),
        )

    def _is_task_enabled(self, task: SideTask) -> bool:
        """检查 task 是否启用（总开关 + side_model 存在 + 单 task 开关）。"""
        if not self._config.get("side", {}).get("enabled", False):
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

    def fire_and_forget(self, task_name: str, **kwargs: Any) -> None:
        """异步执行 task，不等待结果。无运行中 event loop 时安全跳过。"""
        coro = self.run_task(task_name, **kwargs)
        try:
            asyncio.create_task(coro)
        except RuntimeError:
            coro.close()  # 避免 RuntimeWarning: coroutine was never awaited
            logger.warning("fire_and_forget: 没有运行中的 event loop，跳过 task '%s'", task_name)

    def should_run_pref_detection(self) -> bool:
        """检查是否应该运行偏好检测（基于间隔）。"""
        raw_interval = (
            self._config.get("side", {})
            .get("tasks", {})
            .get("pref_detection", {})
            .get("interval", 5)
        )
        interval = _sanitize_interval(raw_interval)
        return self._user_message_count > 0 and self._user_message_count % interval == 0

    def on_user_message(self) -> None:
        """用户消息计数器递增。"""
        self._user_message_count += 1

    def get_side_model(self) -> str:
        """返回 side 模型 ID。"""
        return self._side_model

    @property
    def enabled(self) -> bool:
        """side 层是否启用。"""
        return self._config.get("side", {}).get("enabled", False)
