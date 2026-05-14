"""CosyVoice v3 Flash WebSocket TTS 客户端。

通过阿里云 DashScope WebSocket API 实时流式语音合成。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import AsyncIterator

import websockets

logger = logging.getLogger(__name__)

# DashScope CosyVoice WebSocket 端点
COSYVOICE_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
COSYVOICE_MAX_CHARS = 180


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
        segments = self._prepare_text_segments(text)
        if not segments:
            return

        for segment in segments:
            produced = 0
            async for chunk in self._synthesize_one(segment):
                produced += len(chunk)
                yield chunk

            # 单段无音频时降级重试一次（更短、更干净），避免整段静默
            if produced == 0:
                fallback = self._fallback_text(segment)
                if fallback and fallback != segment:
                    logger.warning("CosyVoice: empty audio, retrying with fallback text")
                    async for chunk in self._synthesize_one(fallback):
                        yield chunk

    @staticmethod
    def _normalize_text(text: str) -> str:
        """规整文本，避免 CosyVoice 因非法输入返回 418。"""
        if not text:
            return ""
        normalized = text.replace("\r", " ").replace("\n", " ")
        normalized = normalized.replace("…", "。").replace("—", "-").replace("–", "-")
        normalized = normalized.replace("∴", " ").replace("⏺", " ").replace("•", " ")
        # 去除 markdown/code 标记与控制字符
        normalized = re.sub(r"`{1,3}.*?`{1,3}", " ", normalized)
        normalized = re.sub(r"[*_#~]+", " ", normalized)
        normalized = re.sub(r"[\x00-\x1f\x7f]", " ", normalized)
        # 仅保留常见中英数与基本标点，其他字符置空格
        normalized = re.sub(
            r"[^0-9A-Za-z\u4e00-\u9fff"
            r"，。！？；：、,.!?;:'\"“”‘’（）()《》〈〉【】\[\]\- ]+",
            " ",
            normalized,
        )
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _prepare_text_segments(self, text: str) -> list[str]:
        """预处理并分段，控制单次请求长度。"""
        normalized = self._normalize_text(text)
        if not normalized:
            return []

        # 优先按句切分，不足时再按长度切
        parts = re.split(r"(?<=[。！？；!?;])", normalized)
        segments: list[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) <= COSYVOICE_MAX_CHARS:
                segments.append(part)
                continue
            start = 0
            while start < len(part):
                end = start + COSYVOICE_MAX_CHARS
                segments.append(part[start:end].strip())
                start = end

        # 过滤掉几乎不可读的碎片，避免触发 invalid text
        filtered = []
        for seg in segments:
            if not self._is_speakable_segment(seg):
                continue
            filtered.append(seg)
        return filtered

    @staticmethod
    def _is_speakable_segment(text: str) -> bool:
        """判断片段是否可送入 CosyVoice。"""
        if len(text) < 2:
            return False
        if not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", text):
            return False
        if re.fullmatch(r"[.\-_,，。！？!?;；:：\s]+", text):
            return False

        has_cjk = re.search(r"[\u4e00-\u9fff]", text) is not None
        if has_cjk:
            return True
        # 纯英文/数字片段过短时跳过，避免 418
        return len(text) >= 8

    @staticmethod
    def _fallback_text(text: str) -> str:
        """失败重试用的简化文本。"""
        simplified = re.sub(r"[“”\"'‘’（）()《》〈〉【】\[\]，,；;：:]+", " ", text)
        simplified = re.sub(r"\s+", " ", simplified).strip()
        if len(simplified) > 80:
            simplified = simplified[:80]
        if not CosyVoiceClient._is_speakable_segment(simplified):
            return ""
        return simplified

    async def _synthesize_one(self, text: str, max_retries: int = 2) -> AsyncIterator[bytes]:
        """合成单个文本片段，网络错误自动重试。"""
        for attempt in range(max_retries + 1):
            try:
                async for chunk in self._synthesize_one_attempt(text):
                    yield chunk
                return  # 成功，退出重试循环
            except (ConnectionResetError, OSError, websockets.exceptions.ConnectionClosed) as exc:
                if attempt < max_retries:
                    wait = 0.5 * (attempt + 1)
                    logger.warning("CosyVoice: connection error (attempt %d/%d), retrying in %.1fs: %s",
                                   attempt + 1, max_retries + 1, wait, exc)
                    await asyncio.sleep(wait)
                else:
                    logger.error("CosyVoice: all %d retries exhausted: %s", max_retries + 1, exc)

    async def _synthesize_one_attempt(self, text: str) -> AsyncIterator[bytes]:
        """单次合成尝试。网络异常向上抛出，由 _synthesize_one 负责重试。"""
        task_id = str(uuid.uuid4())
        headers = {"Authorization": f"Bearer {self._api_key}"}
        logger.info("CosyVoice: Starting synthesis for text: '%s...' (task_id=%s)", text[:30], task_id)

        logger.info("CosyVoice: Connecting to WebSocket: %s", self._url)
        async with websockets.connect(
            self._url,
            additional_headers=headers,
            max_size=2**24,
        ) as ws:
            logger.info("CosyVoice: WebSocket connected successfully")

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
            logger.info("CosyVoice: Sent run-task message")

            # 2. 等待 task-started
            resp = await ws.recv()
            data = json.loads(resp)
            event = data.get("header", {}).get("event", "")
            logger.info("CosyVoice: Received event: %s", event)

            if event != "task-started":
                if event == "task-failed":
                    error = data.get("header", {}).get("error_message", "unknown")
                    logger.error("CosyVoice task failed before streaming: %s", error)
                else:
                    logger.error("CosyVoice: unexpected start event: %s", event)
                return

            logger.info("CosyVoice: Task started, sending text...")

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
            logger.info("CosyVoice: Sent continue-task with text")

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
            logger.info("CosyVoice: Sent finish-task, waiting for audio...")

            # 5. 接收音频数据直到 task-finished
            audio_chunks = 0
            while True:
                msg = await ws.recv()
                if isinstance(msg, bytes):
                    audio_chunks += 1
                    if audio_chunks <= 3:
                        logger.info("CosyVoice: Received audio chunk %d, size=%d bytes", audio_chunks, len(msg))
                    yield msg
                else:
                    data = json.loads(msg)
                    event = data.get("header", {}).get("event", "")
                    if event == "task-finished":
                        logger.info("CosyVoice: Task finished, total audio chunks=%d", audio_chunks)
                        break
                    elif event == "result-generated":
                        continue
                    elif event == "task-failed":
                        error = data.get("header", {}).get("error_message", "unknown")
                        logger.error("CosyVoice task failed: %s", error)
                        break


def create_cosyvoice_client(config: dict) -> CosyVoiceClient | None:
    """从 Brix 配置创建 CosyVoice 客户端。"""
    voice_cfg = config.get("voice", {})
    api_key_env = voice_cfg.get("tts_api_key_env", "ALI_API_KEY")
    api_key = os.environ.get(api_key_env, "")

    if not api_key:
        # 兜底加载 .env：有些入口不会经过 main.py 的 load_dotenv()
        try:
            from dotenv import load_dotenv

            load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
            load_dotenv(override=False)
            api_key = os.environ.get(api_key_env, "")
        except Exception:
            pass

    if not api_key:
        logger.warning("CosyVoice: API key not found (env: %s)", api_key_env)
        return None

    return CosyVoiceClient(
        api_key=api_key,
        model=voice_cfg.get("tts_model", "cosyvoice-v3-flash"),
        voice=voice_cfg.get("tts_voice", "longxiaochun"),
        sample_rate=voice_cfg.get("tts_sample_rate", 24000),
    )
