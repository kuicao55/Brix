"""Command 基础类型定义。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CommandType(Enum):
    """命令类型枚举。"""

    SYSTEM = "system"  # 硬编码逻辑 (/quit, /clear)
    SKILL = "skill"  # prompt 注入 (/commit, /review)


class CommandResultType(Enum):
    """命令执行结果类型。"""

    NONE = "none"  # 无后续操作
    QUIT = "quit"  # 退出 REPL
    CLEAR = "clear"  # 清空会话历史
    PROMPT = "prompt"  # 注入 prompt（Skill 专用）


@dataclass
class CommandMeta:
    """命令元数据。"""

    name: str  # 唯一标识符，不含 / 前缀
    description: str  # 人类可读描述
    type: CommandType  # 命令类型
    when_to_use: str = ""  # LLM 匹配用描述
    user_invocable: bool = True  # 用户可否 /name 调用
    disable_model_invocation: bool = False  # 是否禁止 LLM 调用


@dataclass
class CommandResult:
    """命令执行结果。"""

    type: CommandResultType
    prompt_text: str = ""  # type=PROMPT 时的 prompt 内容
    allowed_tools: list[str] | None = None  # 工具白名单覆盖
    model: str | None = None  # 模型覆盖


@dataclass
class CommandContext:
    """命令执行上下文。"""

    session_id: str = ""
    data_dir: str = ""
    console: Any = None  # Rich Console 实例
    config: dict = field(default_factory=dict)
    memory: Any = None  # MemoryProvider 实例
    llm_client: Any = None  # LLMClient 实例


class Command(ABC):
    """命令抽象基类。"""

    @property
    @abstractmethod
    def meta(self) -> CommandMeta:
        """返回命令元数据。"""
        ...

    @abstractmethod
    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        """执行命令。

        Args:
            args: 用户传入的参数字符串（去掉命令名后的部分）
            context: 执行上下文

        Returns:
            CommandResult，CLI 根据 type 决定后续行为
        """
        ...
