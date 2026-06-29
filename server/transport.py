"""WebSocket Server — Unix Socket + 可选 TCP。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import websockets
from websockets.asyncio.server import ServerConnection

from protocol.types import ClientMessage, ServerEvent
from server.app import BrixServerApp
from server.session_handler import SessionHandler, SessionContext

logger = logging.getLogger(__name__)


class BrixServer:
    """WebSocket Server — Unix Socket + 可选 TCP。"""

    def __init__(
        self,
        app: BrixServerApp,
        socket_path: str = "~/.brix/server.sock",
        host: str = "0.0.0.0",
        port: int | None = None,
    ) -> None:
        self._app = app
        self._socket_path = Path(socket_path).expanduser()
        self._host = host
        self._port = port
        self._local_server = None
        self._remote_server = None
        self._connections: dict[str, ServerConnection] = {}

    async def start(self) -> None:
        """启动 WebSocket Server。"""
        # 确保 socket 目录存在
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        # 清理旧的 socket 文件
        if self._socket_path.exists():
            self._socket_path.unlink()

        # 启动 Unix Socket server
        self._local_server = await websockets.unix_serve(
            self._handle_connection,
            str(self._socket_path),
        )
        logger.info("Listening on unix://%s", self._socket_path)

        # 可选：启动 TCP server
        if self._port:
            self._remote_server = await websockets.serve(
                self._handle_connection,
                self._host,
                self._port,
            )
            logger.info("Listening on ws://%s:%d", self._host, self._port)

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        """处理单个 WebSocket 连接。"""
        client_id = str(uuid.uuid4())
        ctx = self._app.create_session_context(client_id)
        self._connections[client_id] = websocket
        logger.info("Client connected: %s", client_id)

        try:
            async for message in websocket:
                if isinstance(message, str):
                    await self._handle_message(message, ctx, websocket)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Client disconnected: %s", client_id)
        except Exception:
            logger.exception("Error handling client %s", client_id)
        finally:
            self._app.release_session_context(client_id)
            self._connections.pop(client_id, None)

    async def _handle_message(
        self, raw: str, ctx: SessionContext, ws: ServerConnection
    ) -> None:
        """处理单条消息。"""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
            return

        msg_type = msg.get("type")
        if not msg_type:
            await ws.send(json.dumps({"type": "error", "message": "Missing type field"}))
            return

        try:
            if msg_type == "chat":
                async for event in self._app.handle_chat(msg.get("content", ""), ctx):
                    await ws.send(json.dumps(event))
            elif msg_type == "voice_input":
                async for event in self._app.handle_chat(msg.get("content", ""), ctx):
                    await ws.send(json.dumps(event))
            elif msg_type == "command":
                result = await self._app.handle_command(
                    msg.get("command", "").lstrip("/"),
                    msg.get("args", ""),
                    ctx,
                )
                await ws.send(json.dumps(result))
            elif msg_type == "list_sessions":
                sessions = ctx.memory.list_sessions()
                await ws.send(
                    json.dumps(
                        {
                            "type": "command_result",
                            "command": "list_sessions",
                            "data": {"sessions": sessions},
                        }
                    )
                )
            elif msg_type == "resume_session":
                session_id = msg.get("session_id", "")
                try:
                    messages = ctx.memory.resume_session(session_id)
                    await ws.send(
                        json.dumps(
                            {
                                "type": "command_result",
                                "command": "resume_session",
                                "data": {
                                    "resumed_session_id": session_id,
                                    "messages": messages,
                                },
                            }
                        )
                    )
                except FileNotFoundError:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "error",
                                "message": f"Session not found: {session_id}",
                            }
                        )
                    )
            elif msg_type == "create_session":
                session_id = ctx.memory.create_session()
                await ws.send(
                    json.dumps(
                        {
                            "type": "command_result",
                            "command": "create_session",
                            "data": {"session_id": session_id},
                        }
                    )
                )
            elif msg_type == "get_status":
                await ws.send(
                    json.dumps(
                        {
                            "type": "status",
                            "data": {
                                "active_sessions": len(self._connections),
                                "local_socket": str(self._socket_path),
                                "remote_port": self._port,
                            },
                        }
                    )
                )
            else:
                await ws.send(
                    json.dumps({"type": "error", "message": f"Unknown message type: {msg_type}"})
                )
        except Exception as exc:
            logger.exception("Error handling message type %s", msg_type)
            await ws.send(json.dumps({"type": "error", "message": str(exc)}))

    async def stop(self) -> None:
        """停止 Server。"""
        logger.info("Stopping server...")
        # 关闭所有连接
        for client_id, ws in list(self._connections.items()):
            try:
                await ws.close()
            except Exception:
                pass
        self._connections.clear()

        # 停止服务器
        if self._local_server:
            self._local_server.close()
            await self._local_server.wait_closed()
        if self._remote_server:
            self._remote_server.close()
            await self._remote_server.wait_closed()

        # 清理 socket 文件
        if self._socket_path.exists():
            self._socket_path.unlink()
        logger.info("Server stopped")

    @property
    def socket_path(self) -> Path:
        return self._socket_path
