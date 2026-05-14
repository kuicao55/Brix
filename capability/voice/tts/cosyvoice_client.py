"""CosyVoice v3 Flash WebSocket TTS 客户端。

通过阿里云 DashScope WebSocket API 实时流式语音合成。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import AsyncIterator

import websockets

logger = logging.getLogger(__name__)

# DashScope CosyVoice WebSocket 端点
COSYVOICE_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"


class CosyVoiceClient:
    """CosyVoice v3 Flash 流式 TTS 客户端。

    使用 WebSocket 双工模式，按句合成为 PCM 音频流。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "cosyvoice-v3-flash",
        voice: str = "longxiaochun",
        sample_rate: int = 24000,
        url: str = COSYVOICE_WS_URL,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._voice = voice
        self._sample_rate = sample_rate
        self._url = url

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """流式合成文本，yield PCM 音频 chunks。

        每次调用建立一个新 WebSocket 连接，完成一个完整任务。
        """
        if not text.strip():
            return

        task_id = str(uuid.uuid4())
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with websockets.connect(
                self._url,
                additional_headers=headers,
                max_size=2**24,
            ) as ws:
                # 1. 发送 run-task
                run_msg = {
                    "header": {
                        "action": "run-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {
                        "task_group": "audio",
                        "task": "tts",
                        "function": "SpeechSynthesizer",
                        "model": self._model,
                        "parameters": {
                            "text_type": "PlainText",
                            "voice": self._voice,
                            "format": "pcm",
                            "sample_rate": self._sample_rate,
                        },
                        "input": {},
                    },
                }
                await ws.send(json.dumps(run_msg))

                # 2. 等待 task-started
                resp = await ws.recv()
                data = json.loads(resp)
                event = data.get("header", {}).get("event", "")
                if event != "task-started":
                    logger.error("CosyVoice: unexpected event: %s", event)
                    return

                # 3. 发送 continue-task（文本）
                continue_msg = {
                    "header": {
                        "action": "continue-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {
                        "input": {
                            "text": text,
                        },
                    },
                }
                await ws.send(json.dumps(continue_msg))

                # 4. 发送 finish-task
                finish_msg = {
                    "header": {
                        "action": "finish-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {
                        "input": {},
                    },
                }
                await ws.send(json.dumps(finish_msg))

                # 5. 接收音频数据直到 task-finished
                while True:
                    msg = await ws.recv()
                    if isinstance(msg, bytes):
                        # 二进制音频数据
                        yield msg
                    else:
                        data = json.loads(msg)
                        event = data.get("header", {}).get("event", "")
                        if event == "task-finished":
                            break
                        elif event == "result-generated":
                            # 中间结果，继续接收
                            continue
                        elif event == "task-failed":
                            error = data.get("header", {}).get("error_message", "unknown")
                            logger.error("CosyVoice task failed: %s", error)
                            break

        except websockets.exceptions.ConnectionClosed as exc:
            logger.error("CosyVoice WebSocket closed: %s", exc)
        except Exception as exc:
            logger.error("CosyVoice error: %s", exc, exc_info=True)


def create_cosyvoice_client(config: dict) -> CosyVoiceClient | None:
    """从 Brix 配置创建 CosyVoice 客户端。"""
    voice_cfg = config.get("voice", {})
    api_key_env = voice_cfg.get("tts_api_key_env", "ALI_API_KEY")
    api_key = os.environ.get(api_key_env, "")

    if not api_key:
        logger.warning("CosyVoice: API key not found (env: %s)", api_key_env)
        return None

    return CosyVoiceClient(
        api_key=api_key,
        model=voice_cfg.get("tts_model", "cosyvoice-v3-flash"),
        voice=voice_cfg.get("tts_voice", "longxiaochun"),
        sample_rate=voice_cfg.get("tts_sample_rate", 24000),
    )
