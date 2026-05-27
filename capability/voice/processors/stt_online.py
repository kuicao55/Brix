"""OnlineSTTProcessor — Qwen-ASR Realtime 在线语音识别。

通过阿里云 DashScope WebSocket API 实时语音识别。
使用服务端 VAD 模式，自动返回 interim（实时）和 final（最终）转录结果。

不依赖 DashScope SDK，直接使用 websockets 库连接。
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import queue
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from capability.voice.pipeline.frames import CleanedTextFrame, VoiceStateFrame

logger = logging.getLogger(__name__)

# Qwen-ASR Realtime WebSocket 端点
QWEN_ASR_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"


class OnlineSTTProcessor:
    """Qwen-ASR Realtime 在线语音识别处理器。

    使用服务端 VAD 模式：
    - 持续向服务端发送音频
    - 服务端自动检测语音起止
    - interim 转录通过 on_interim_text 回调实时返回
    - final 转录在服务端 speech_stopped 后自动产生

    接口与 STTProcessor 部分兼容：
    - process_frame_sync: 缓冲音频 + 发送服务端，speech_end 时等待 final 结果
    - start / stop / reset: 生命周期管理
    - get_buffer_audio: 返回空（不需要本地 interim）
    """

    def __init__(
        self,
        api_key: str,
        model: str = "qwen3-asr-flash-realtime",
        language: str = "zh",
        url: str = QWEN_ASR_WS_URL,
        on_interim_text: Callable[[str], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language
        self._url = url
        self._audio_buffer = bytearray()

        # 回调
        self._on_interim_text = on_interim_text

        # WebSocket 连接
        self._ws: Any = None
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        self._ws_thread: threading.Thread | None = None
        self._connected = threading.Event()
        self._session_ready = threading.Event()

        # final 结果队列（服务端 speech_stopped 后产生）
        self._final_queue: queue.Queue[str | None] = queue.Queue(maxsize=5)

        self._running = False
        self._shutdown = threading.Event()  # 用于中断阻塞等待

    def start(self) -> None:
        """建立 WebSocket 连接并配置会话。"""
        if self._running:
            return
        self._running = True
        self._shutdown.clear()

        self._ws_loop = asyncio.new_event_loop()
        self._ws_thread = threading.Thread(
            target=self._run_ws_loop,
            daemon=True,
            name="stt-online-ws",
        )
        self._ws_thread.start()

        if not self._session_ready.wait(timeout=15):
            logger.error("OnlineSTT: session ready timeout")
            self._running = False

    def _run_ws_loop(self) -> None:
        asyncio.set_event_loop(self._ws_loop)
        try:
            self._ws_loop.run_until_complete(self._ws_main())
        except Exception as exc:
            logger.error("OnlineSTT: WebSocket loop error: %s", exc)
        finally:
            self._ws_loop.close()

    async def _ws_main(self) -> None:
        import websockets

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        url = f"{self._url}?model={self._model}"

        try:
            async with websockets.connect(
                url,
                additional_headers=headers,
                max_size=2**24,
            ) as ws:
                self._ws = ws
                self._connected.set()
                logger.info("OnlineSTT: WebSocket connected")

                # 服务端 VAD 模式：自动检测语音起止 + 自动返回转录结果
                session_update = {
                    "event_id": f"event_{uuid.uuid4().hex[:8]}",
                    "type": "session.update",
                    "session": {
                        "modalities": ["text"],
                        "input_audio_format": "pcm",
                        "sample_rate": 16000,
                        "input_audio_transcription": {
                            "language": self._language,
                        },
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.0,
                            "silence_duration_ms": 400,
                        },
                    },
                }
                await ws.send(json.dumps(session_update))
                logger.info("OnlineSTT: session.update sent (server VAD mode)")

                async for message in ws:
                    if not self._running:
                        break
                    self._handle_message(message)

        except Exception as exc:
            logger.error("OnlineSTT: WebSocket error: %s", exc)
        finally:
            self._ws = None
            self._connected.clear()
            self._session_ready.set()
            logger.info("OnlineSTT: WebSocket closed")

    def _handle_message(self, raw: str | bytes) -> None:
        """处理服务端消息。"""
        if isinstance(raw, bytes):
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type", "")

        if msg_type == "session.created":
            logger.info("OnlineSTT: session created: %s",
                       data.get("session", {}).get("id", ""))
            self._session_ready.set()

        elif msg_type == "session.updated":
            logger.info("OnlineSTT: session updated")
            self._session_ready.set()

        elif msg_type == "conversation.item.input_audio_transcription.text":
            # 实时中间结果 — 直接通过回调发送
            text = data.get("text", "")
            stash = data.get("stash", "")
            interim = (text + stash).strip()
            if interim and self._on_interim_text:
                self._on_interim_text(interim)

        elif msg_type == "conversation.item.input_audio_transcription.completed":
            # 最终结果 — 放入队列，由 process_frame_sync 消费
            transcript = data.get("transcript", "")
            logger.info("OnlineSTT: final transcript: '%s'", transcript[:50])
            try:
                self._final_queue.put_nowait(transcript)
            except queue.Full:
                # 队列满，丢弃最旧的
                try:
                    self._final_queue.get_nowait()
                except queue.Empty:
                    pass
                self._final_queue.put_nowait(transcript)

        elif msg_type == "input_audio_buffer.speech_started":
            logger.debug("OnlineSTT: server speech_started")

        elif msg_type == "input_audio_buffer.speech_stopped":
            logger.debug("OnlineSTT: server speech_stopped")

        elif msg_type == "error":
            error = data.get("error", {})
            logger.error("OnlineSTT: server error: %s",
                        error.get("message", data))

        elif msg_type == "session.finished":
            logger.info("OnlineSTT: session finished")

    def stop(self) -> None:
        self._running = False
        self._shutdown.set()  # 中断阻塞等待
        # 向 final_queue 放一个空值，唤醒可能阻塞的 get()
        try:
            self._final_queue.put_nowait(None)
        except queue.Full:
            pass
        if self._ws_loop is not None:
            if self._ws is not None:
                asyncio.run_coroutine_threadsafe(
                    self._close_ws(), self._ws_loop
                )
            if self._ws_thread is not None:
                self._ws_thread.join(timeout=3)
            self._ws_loop = None
            self._ws_thread = None
        self._connected.clear()
        self._session_ready.clear()
        logger.info("OnlineSTT: stopped")

    async def _close_ws(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass

    def process_frame_sync(self, frame: Any) -> list:
        """处理音频帧。

        服务端 VAD 模式下：
        - 音频帧：缓冲 + 发送到服务端，返回空
        - speech_start：清空旧结果队列
        - speech_end：flush 缓冲区 + 手动 commit，等待服务端 final 结果
        """
        if isinstance(frame, VoiceStateFrame):
            if frame.state == "speech_start":
                # 清空旧结果，防止上一轮残留
                while not self._final_queue.empty():
                    try:
                        self._final_queue.get_nowait()
                    except queue.Empty:
                        break
                return []

            elif frame.state == "speech_end":
                return self._handle_speech_end()

        elif hasattr(frame, "audio"):
            self._audio_buffer.extend(frame.audio)
            # 持续发送音频到服务端（服务端 VAD 自动检测语音边界）
            if self._connected.is_set() and self._ws is not None:
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self._send_audio(frame.audio, commit=False),
                        self._ws_loop,
                    )
                    future.result(timeout=2)
                except Exception as exc:
                    logger.debug("OnlineSTT: send error: %s", exc)

        return []

    def _handle_speech_end(self) -> list:
        """处理 speech_end：等待服务端自动 commit 的 final 结果。

        服务端 VAD 模式下，服务端检测到 speech_stopped 后会自动 commit 并产生
        final 结果，无需也不应手动 commit（否则会报 "Error committing" 错误）。
        """
        if self._shutdown.is_set():
            return []
        if not self._connected.is_set() or self._ws is None:
            logger.warning("OnlineSTT: not connected on speech_end")
            return []

        # 清空本地音频缓冲（服务端已通过实时 append 收到所有音频）
        self._audio_buffer.clear()

        # 等待服务端自动 commit 的 final 结果
        # 分段等待，每 0.5s 检查 shutdown 信号，确保 Ctrl+C 可中断
        for _ in range(16):  # 最多 8s
            if self._shutdown.is_set():
                logger.info("OnlineSTT: shutdown during final wait")
                return []
            try:
                text = self._final_queue.get(timeout=0.5)
                if text:
                    return [CleanedTextFrame(text=text, raw_text=text)]
                # None 是 shutdown 唤醒信号
                if text is None and self._shutdown.is_set():
                    return []
            except queue.Empty:
                continue
        logger.warning("OnlineSTT: final result timeout (8s)")
        return []

    async def _flush_and_commit(self) -> None:
        """flush 缓冲区音频并发送 commit。"""
        if self._ws is None:
            return

        # 发送剩余音频
        if self._audio_buffer:
            audio_b64 = base64.b64encode(bytes(self._audio_buffer)).decode("ascii")
            self._audio_buffer = bytearray()
            await self._ws.send(json.dumps({
                "event_id": f"event_{uuid.uuid4().hex[:8]}",
                "type": "input_audio_buffer.append",
                "audio": audio_b64,
            }))

        # 发送 commit（告诉服务端：这段音频说完了，请处理）
        await self._ws.send(json.dumps({
            "event_id": f"event_{uuid.uuid4().hex[:8]}",
            "type": "input_audio_buffer.commit",
        }))
        logger.debug("OnlineSTT: flush + commit sent")

    async def _send_audio(self, audio_bytes: bytes, commit: bool = False) -> None:
        """发送音频到服务端。"""
        if self._ws is None:
            return

        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        event = {
            "event_id": f"event_{uuid.uuid4().hex[:8]}",
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        }
        await self._ws.send(json.dumps(event))

        if commit:
            commit_event = {
                "event_id": f"event_{uuid.uuid4().hex[:8]}",
                "type": "input_audio_buffer.commit",
            }
            await self._ws.send(json.dumps(commit_event))

    def transcribe_interim(self, audio_bytes: bytes, cancel: Any = None) -> str:
        """服务端 VAD 模式下不需要本地 interim，返回空。"""
        return ""

    def get_buffer_audio(self) -> bytes:
        return bytes(self._audio_buffer)

    def reset(self) -> None:
        self._audio_buffer.clear()


def create_online_stt_processor(config: dict) -> OnlineSTTProcessor | None:
    """从 Brix 配置创建 OnlineSTTProcessor。"""
    voice_cfg = config.get("voice", {})
    api_key_env = voice_cfg.get("stt_online_api_key_env", "ALI_API_KEY")
    api_key = os.environ.get(api_key_env, "")

    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
            load_dotenv(override=False)
            api_key = os.environ.get(api_key_env, "")
        except Exception:
            pass

    if not api_key:
        logger.warning("OnlineSTT: API key not found (env: %s)", api_key_env)
        return None

    return OnlineSTTProcessor(
        api_key=api_key,
        model=voice_cfg.get("stt_online_model", "qwen3-asr-flash-realtime"),
        language=voice_cfg.get("stt_online_language", "zh"),
    )
