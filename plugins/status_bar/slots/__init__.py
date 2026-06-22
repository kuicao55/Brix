"""内置 StatusSlot 实现 + 配置驱动的加载函数。"""

from __future__ import annotations

import logging
from typing import Any

from plugins.status_bar import StatusSlot
from plugins.status_bar.slots.model_slot import ModelSlot
from plugins.status_bar.slots.task_slot import TaskSlot

logger = logging.getLogger(__name__)

# 所有内置 slot 注册表
ALL_SLOTS: list[StatusSlot] = [
    ModelSlot(),
    TaskSlot(),
]


def _check_strict_bool(value: Any) -> bool:
    """严格布尔检查：仅接受 bool 类型，非布尔值视为 False 并警告。"""
    if isinstance(value, bool):
        return value
    logger.warning(
        "status_bar.slots.*.enabled=%r 不是严格布尔值 (type=%s)，视为 disabled",
        value,
        type(value).__name__,
    )
    return False


def _is_slot_enabled(slot: StatusSlot, config: dict) -> bool:
    """检查 slot 是否在配置中启用。

    读取 config.status_bar.slots.{slot.name}.enabled。
    缺失配置时默认启用（向后兼容）。
    """
    try:
        value = config["status_bar"]["slots"][slot.name]["enabled"]
    except (KeyError, TypeError):
        # 配置缺失时默认启用，保证向后兼容
        return True
    return _check_strict_bool(value)


def load_enabled_slots(config: dict) -> list[StatusSlot]:
    """根据 settings.yaml 配置返回所有已启用的 slot。

    配置路径：status_bar.slots.{name}.enabled: true/false
    缺失配置的 slot 默认启用（向后兼容）。
    """
    return [slot for slot in ALL_SLOTS if _is_slot_enabled(slot, config)]
