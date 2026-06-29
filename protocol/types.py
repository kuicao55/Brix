"""Server-Client 通信的消息类型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any
import json


@dataclass
class ClientMessage:
    """Client → Server 消息。

    所有消息为 JSON，顶层字段 `type` 标识消息类型。
    """

    type: str  # chat | command | list_sessions | resume_session | create_session | get_status | voice_input
    content: str = ""  # chat / voice_input 的文本内容
    command: str = ""  # /slash 命令
    args: str = ""  # 命令参数
    session_id: str = ""  # resume_session 的 session ID

    def to_json(self) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "ClientMessage":
        """从 JSON 字符串反序列化。"""
        data = json.loads(raw)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ServerEvent:
    """Server → Client 事件。

    所有事件为 JSON，顶层字段 `type` 标识事件类型。
    """

    type: str  # thinking_delta | text_delta | tool_call | tool_result | stream_end | command_result | status | error | server_event
    text: str = ""  # thinking_delta / text_delta 的文本
    id: str = ""  # tool_call / tool_result 的 ID
    name: str = ""  # tool_call / tool_result 的工具名
    input: dict = field(default_factory=dict)  # tool_call 的输入参数
    result: str = ""  # tool_result 的结果
    ms: int = 0  # tool_result 的耗时
    is_error: bool = False  # tool_result 是否为错误
    command: str = ""  # command_result 的命令名
    data: dict = field(default_factory=dict)  # command_result / status 的数据
    message: str = ""  # error 的错误信息
    code: str = ""  # error 的错误码
    event: str = ""  # server_event 的事件名

    def to_json(self) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "ServerEvent":
        """从 JSON 字符串反序列化。"""
        data = json.loads(raw)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServerEvent":
        """从字典创建。"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
