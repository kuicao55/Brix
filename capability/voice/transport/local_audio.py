"""LocalAudioTransport — PyAudio 麦克风/扬声器管理。

PyAudio 的回调在独立线程中运行，通过 asyncio.Queue 桥接到主 event loop。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

try:
    import pyaudio
except ImportError:
    pyaudio = None  # type: ignore[assignment]

from capability.voice.config import VoiceConfig

logger = logging.getLogger(__name__)


class LocalAudioTransport:
    """本地音频传输层 — 管理 PyAudio 麦克风输入。"""

    def __init__(self, config: VoiceConfig) -> None:
        self._config = config
        self._pa: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None
        self._active = False
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self) -> None:
        """启动麦克风采集。"""
        if self._active:
            return

        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._config.channels,
            rate=self._config.sample_rate,
            input=True,
            frames_per_buffer=self._config.chunk_samples,
            stream_callback=self._audio_callback,
        )
        self._active = True
        logger.info(
            "LocalAudioTransport started: %dHz, %d ch, %d samples/chunk",
            self._config.sample_rate,
            self._config.channels,
            self._config.chunk_samples,
        )

    async def stop(self) -> None:
        """停止麦克风采集，释放资源。"""
        if not self._active:
            return

        self._active = False
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None
        logger.info("LocalAudioTransport stopped")

    def _audio_callback(
        self,
        in_data: bytes | None,
        frame_count: int,
        time_info: Any,
        status: int,
    ) -> tuple[None, int]:
        """PyAudio 回调 — 在独立线程中运行。

        将音频数据放入 asyncio.Queue，由主 event loop 消费。
        """
        if in_data and self._active:
            try:
                self.audio_queue.put_nowait(in_data)
            except asyncio.QueueFull:
                try:
                    self.audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    self.audio_queue.put_nowait(in_data)
                except asyncio.QueueFull:
                    pass
        return (None, pyaudio.paContinue)
