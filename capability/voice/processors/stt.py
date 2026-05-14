"""STTProcessor — faster-whisper 语音识别。

语音结束后整段转录（非实时流式），中文效果更好。
使用持久化子进程运行 faster-whisper，隔离 ctranslate2 与 PyTorch 的 OpenMP 冲突。
模型只在子进程中加载一次，后续转录复用。
"""

from __future__ import annotations

import logging
import multiprocessing as mp
from typing import Any

import numpy as np

from capability.voice.pipeline.frames import CleanedTextFrame, VoiceStateFrame

logger = logging.getLogger(__name__)


def _stt_persistent_worker(
    model_name: str,
    language: str,
    device: str,
    compute_type: str,
    request_queue: mp.Queue,
    result_queue: mp.Queue,
) -> None:
    """持久化子进程 — 加载模型一次，循环接收转录请求。"""
    import os

    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    from faster_whisper import WhisperModel

    logger.info("STT worker: loading model %s (%s/%s)...", model_name, device, compute_type)
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    logger.info("STT worker: model loaded, ready")

    while True:
        item = request_queue.get()
        if item is None:
            # 停止信号
            break

        request_id, audio_bytes = item
        try:
            audio_array = (
                np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )
            segments, info = model.transcribe(
                audio_array,
                language=language,
                beam_size=5,
                vad_filter=False,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            result_queue.put((request_id, "ok", text))
        except Exception as exc:
            result_queue.put((request_id, "error", str(exc)))


class STTProcessor:
    """faster-whisper 语音识别处理器。"""

    def __init__(
        self,
        model_name: str = "small",
        language: str = "zh",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self._model_name = model_name
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._audio_buffer = bytearray()

        self._ctx = mp.get_context("spawn")
        self._request_queue: mp.Queue | None = None
        self._result_queue: mp.Queue | None = None
        self._worker: mp.Process | None = None
        self._request_counter = 0

    def start(self) -> None:
        """启动持久化 STT 子进程。"""
        if self._worker is not None:
            return

        self._request_queue = self._ctx.Queue()
        self._result_queue = self._ctx.Queue()
        self._worker = self._ctx.Process(
            target=_stt_persistent_worker,
            args=(
                self._model_name,
                self._language,
                self._device,
                self._compute_type,
                self._request_queue,
                self._result_queue,
            ),
            daemon=True,
        )
        self._worker.start()
        logger.info("STT subprocess started (pid=%d)", self._worker.pid)

    def stop(self) -> None:
        """停止 STT 子进程。"""
        if self._worker is None:
            return

        # 发送停止信号
        if self._request_queue is not None:
            self._request_queue.put(None)

        self._worker.join(timeout=5)
        if self._worker.is_alive():
            self._worker.terminate()
            self._worker.join(timeout=2)

        self._worker = None
        self._request_queue = None
        self._result_queue = None
        logger.info("STT subprocess stopped")

    def _transcribe_audio(self, audio_bytes: bytes) -> str:
        """转录音频数据为文本。发送到持久化子进程。"""
        if not audio_bytes:
            return ""
        if self._worker is None or self._request_queue is None or self._result_queue is None:
            logger.error("STT worker not started")
            return ""

        self._request_counter += 1
        request_id = self._request_counter

        self._request_queue.put((request_id, audio_bytes))

        # 阻塞等待结果（替代 busy-poll）
        try:
            rid, status, result = self._result_queue.get(block=True, timeout=30)
        except Exception:
            logger.error("STT timeout (30s)")
            return ""

        if status == "ok":
            logger.debug("STT result: %s", result[:50])
            return result
        else:
            logger.error("STT error: %s", result)
            return ""

    def get_buffer_audio(self) -> bytes:
        """获取当前缓冲区的音频副本（不清空）。用于 interim 转录。"""
        return bytes(self._audio_buffer)

    def transcribe_interim(self, audio_bytes: bytes) -> str:
        """Interim 转录 — 转录音频但不清理 buffer。用于实时显示。"""
        if not audio_bytes or len(audio_bytes) < 16000:  # <0.5s @ 16kHz
            return ""
        return self._transcribe_audio(audio_bytes)

    def transcribe_sync(self, audio_bytes: bytes) -> list[CleanedTextFrame]:
        """同步转录，返回 CleanedTextFrame 列表。用于测试。"""
        text = self._transcribe_audio(audio_bytes)
        if text:
            return [CleanedTextFrame(text=text, raw_text=text)]
        return []

    def process_frame_sync(self, frame: Any) -> list:
        """同步处理帧，返回产生的帧列表。"""
        if isinstance(frame, VoiceStateFrame) and frame.state == "speech_end":
            audio = bytes(self._audio_buffer)
            self._audio_buffer = bytearray()
            text = self._transcribe_audio(audio)
            if text:
                return [CleanedTextFrame(text=text, raw_text=text)]
            return []
        elif hasattr(frame, "audio"):
            self._audio_buffer.extend(frame.audio)
        return []

    def reset(self) -> None:
        """重置 STT 状态。"""
        self._audio_buffer.clear()
