"""AudioPlayer — PyAudio 扬声器播放，支持流式 PCM 输入。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

try:
    import pyaudio
except ImportError:
    pyaudio = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class AudioPlayer:
    """音频播放器 — 从 asyncio.Queue 读取 PCM chunks 并通过 PyAudio 播放。"""

    def __init__(
        self,
        sample_rate: int = 24000,
        channels: int = 1,
        sample_width: int = 2,  # int16 = 2 bytes
    ) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._sample_width = sample_width
        self._pa: Any = None
        self._stream: Any = None
        self._active = False
        self._play_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=200)
        self._play_task: asyncio.Task | None = None
        self._playback_active = False  # 是否有音频正在播放（包括缓冲区中的音频）

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def is_playing(self) -> bool:
        """是否有音频正在播放（包括缓冲区中的音频）。"""
        return self._playback_active

    async def start(self) -> None:
        """启动播放器。"""
        if self._active:
            return

        if pyaudio is None:
            logger.error("PyAudio not installed, audio playback disabled")
            return

        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=self._sample_rate,
            output=True,
            frames_per_buffer=1024,
        )
        self._active = True
        self._play_task = asyncio.ensure_future(self._play_loop())
        logger.info("AudioPlayer started: %dHz, %d ch", self._sample_rate, self._channels)

    async def stop(self) -> None:
        """停止播放器，释放资源。"""
        if not self._active:
            return

        self._active = False

        # 发送停止信号
        try:
            self._play_queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

        # 等待播放循环结束
        if self._play_task is not None:
            try:
                await asyncio.wait_for(self._play_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._play_task.cancel()
            self._play_task = None

        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

        # 清空队列
        while not self._play_queue.empty():
            try:
                self._play_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        logger.info("AudioPlayer stopped")

    async def play_chunks(self, chunks: Any) -> None:
        """播放异步迭代器产出的 PCM chunks。"""
        # 确保播放循环正在运行
        if self._play_task is None or self._play_task.done():
            self._play_task = asyncio.ensure_future(self._play_loop())

        async for chunk in chunks:
            if not self._active:
                break
            try:
                await asyncio.wait_for(
                    self._play_queue.put(chunk), timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("AudioPlayer: play queue full, dropping chunk")

        # 发送停止信号，让播放循环在 drain 后退出
        try:
            self._play_queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

        # 等待播放循环完成（drain + 清理）
        if self._play_task is not None:
            try:
                await asyncio.wait_for(self._play_task, timeout=30.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            self._play_task = None

    async def _play_loop(self) -> None:
        """播放循环 — 从队列读取数据写入 PyAudio 输出流。"""
        loop = asyncio.get_event_loop()
        bytes_per_second = self._sample_rate * self._channels * self._sample_width
        last_chunk_bytes = 0
        try:
            while self._active:
                try:
                    chunk = await asyncio.wait_for(
                        self._play_queue.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                if chunk is None:
                    # 停止信号
                    break

                # 收到第一个音频块时标记播放开始
                if not self._playback_active:
                    self._playback_active = True

                last_chunk_bytes = len(chunk)

                # 在线程池中执行阻塞的 PyAudio 写入
                try:
                    await loop.run_in_executor(None, self._write_audio, chunk)
                except Exception as exc:
                    logger.error("AudioPlayer write error: %s", exc)

            # 等待最后一个 chunk 播放完成
            # PyAudio 阻塞 write() 已按实时速度写入，只需等待最后一点缓冲数据播完
            if last_chunk_bytes > 0 and bytes_per_second > 0:
                remaining_sec = last_chunk_bytes / bytes_per_second + 0.05
                await asyncio.sleep(remaining_sec)
                logger.debug("AudioPlayer: waited %.2fs for playback to finish", remaining_sec)
        finally:
            self._playback_active = False  # 标记播放结束
            logger.debug("AudioPlayer: playback finished")

    def _write_audio(self, data: bytes) -> None:
        """阻塞写入 PyAudio 流（在线程池中调用）。"""
        if self._stream is not None and self._active:
            self._stream.write(data)
