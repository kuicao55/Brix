"""BrixTransport — WebSocket 客户端封装。"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

import websockets
from websockets.asyncio.client import ClientConnection

from protocol.types import ClientMessage, ServerEvent

logger = logging.getLogger(__name__)


class BrixTransport:
    """统一的 WebSocket 客户端，封装连接、发送、接收。

    使用方式::

        transport = BrixTransport.local()              # Unix Socket
        transport = BrixTransport.remote("192.168.1.100", 8080)  # TCP
        await transport.connect()
        async for event in transport.send_chat("你好"):
            print(event)
    """

    def __init__(self, uri: str, is_unix: bool = False) -> None:
        self._uri = uri
        self._is_unix = is_unix
        self._ws: ClientConnection | None = None

    @classmethod
    def local(cls, socket_path: str = "~/.brix/server.sock") -> "BrixTransport":
        """创建本地 Unix Socket 连接。"""
        from pathlib import Path
        path = Path(socket_path).expanduser()
        return cls(str(path), is_unix=True)

    @classmethod
    def remote(cls, host: str, port: int, ssl: bool = False) -> "BrixTransport":
        """创建远程 TCP 连接。"""
        scheme = "wss" if ssl else "ws"
        return cls(f"{scheme}://{host}:{port}", is_unix=False)

    async def connect(self) -> None:
        """建立 WebSocket 连接。"""
        logger.info("Connecting to %s (unix=%s)", self._uri, self._is_unix)
        if self._is_unix:
            self._ws = await websockets.unix_connect(self._uri)
        else:
            self._ws = await websockets.connect(self._uri)
        logger.info("Connected")

    async def send_chat(self, content: str) -> AsyncGenerator[ServerEvent, None]:
        """发送 chat 消息，返回 server 事件的 async generator。"""
        msg = ClientMessage(type="chat", content=content)
        await self._send(msg.to_json())
        async for raw in self._recv():
            event = ServerEvent.from_json(raw)
            yield event
            if event.type == "stream_end":
                break

    async def send_command(self, command: str, args: str = "") -> ServerEvent:
        """发送 slash 命令，返回结果。"""
        msg = ClientMessage(type="command", command=command, args=args)
        await self._send(msg.to_json())
        raw = await self._recv_one()
        return ServerEvent.from_json(raw)

    async def send_voice_input(self, content: str) -> AsyncGenerator[ServerEvent, None]:
        """发送语音输入文本，返回 server 事件的 async generator。"""
        msg = ClientMessage(type="voice_input", content=content)
        await self._send(msg.to_json())
        async for raw in self._recv():
            event = ServerEvent.from_json(raw)
            yield event
            if event.type == "stream_end":
                break

    async def list_sessions(self) -> ServerEvent:
        """列出所有会话。"""
        msg = ClientMessage(type="list_sessions")
        await self._send(msg.to_json())
        raw = await self._recv_one()
        return ServerEvent.from_json(raw)

    async def resume_session(self, session_id: str) -> ServerEvent:
        """恢复指定会话。"""
        msg = ClientMessage(type="resume_session", session_id=session_id)
        await self._send(msg.to_json())
        raw = await self._recv_one()
        return ServerEvent.from_json(raw)

    async def create_session(self) -> ServerEvent:
        """创建新会话。"""
        msg = ClientMessage(type="create_session")
        await self._send(msg.to_json())
        raw = await self._recv_one()
        return ServerEvent.from_json(raw)

    async def get_status(self) -> ServerEvent:
        """获取 server 状态。"""
        msg = ClientMessage(type="get_status")
        await self._send(msg.to_json())
        raw = await self._recv_one()
        return ServerEvent.from_json(raw)

    async def close(self) -> None:
        """关闭连接。"""
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _send(self, data: str) -> None:
        """发送原始数据。"""
        if not self._ws:
            raise RuntimeError("Not connected")
        await self._ws.send(data)

    async def _recv(self) -> AsyncGenerator[str, None]:
        """接收消息流。"""
        if not self._ws:
            raise RuntimeError("Not connected")
        async for raw in self._ws:
            yield raw

    async def _recv_one(self) -> str:
        """接收单条消息。"""
        if not self._ws:
            raise RuntimeError("Not connected")
        return await self._ws.recv()
