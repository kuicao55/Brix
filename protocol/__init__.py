"""协议层 — Server-Client 通信的消息类型和传输抽象。"""

from protocol.types import ClientMessage, ServerEvent
from protocol.transport import BrixTransport

__all__ = ["ClientMessage", "ServerEvent", "BrixTransport"]
