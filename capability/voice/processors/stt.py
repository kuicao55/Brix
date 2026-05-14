"""STTProcessor — faster-whisper 语音识别。

语音结束后整段转录（非实时流式），中文效果更好。
使用持久化子进程运行 faster-whisper，隔离 ctranslate2 与 PyTorch 的 OpenMP 冲突。
模型只在子进程中加载一次，后续转录复用。

使用两个独立子进程：
- _worker: 用于最终转录（speech_end 后），稳定可靠
- _interim_worker: 用于 interim 转录（实时显示），短超时，可被快速丢弃
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
    cpu_threads: int,
    request_queue: mp.Queue,
    result_queue: mp.Queue,
    tag: str = "final",
) -> None:
    """持久化子进程 — 加载模型一次，循环接收转录请求。"""
    import os
    import sys
    import warnings

    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    warnings.filterwarnings(
        "ignore",
        message="You are sending unauthenticated requests to the HF Hub.*",
    )

    # 子进程需要配置 logging（spawn 上下文不继承父进程配置）
    logging.basicConfig(
        level=logging.WARNING,
        format=f"%(asctime)s [STT-{tag}] %(message)s",
        stream=sys.stderr,
    )

    from faster_whisper import WhisperModel

    logger.debug(
        "Loading model %s (%s/%s, cpu_threads=%d)...",
        model_name, device, compute_type, cpu_threads,
    )
    model = WhisperModel(
        model_name, device=device, compute_type=compute_type,
        cpu_threads=cpu_threads,
    )
    logger.debug("Model loaded, ready")
    result_queue.put((0, "ready", ""))

    while True:
        item = request_queue.get()
        if item is None:
            break

        request_id, audio_bytes = item
        try:
            import time as _time
            _t0 = _time.monotonic()
            audio_array = (
                np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )
            segments, info = model.transcribe(
                audio_array,
                language=language,
                beam_size=1,
                vad_filter=False,
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            _t1 = _time.monotonic()
            audio_dur = len(audio_bytes) / (16000 * 2)
            logger.debug(
                "#%d: audio=%.1fs, transcribe=%dms → '%s'",
                request_id, audio_dur, (_t1 - _t0) * 1000,
                text[:30] if text else "",
            )
            result_queue.put((request_id, "ok", text))
        except Exception as exc:
            result_queue.put((request_id, "error", str(exc)))


class STTProcessor:
    """faster-whisper 语音识别处理器。

    双 worker 架构：
    - _worker: 最终转录，可靠，30s 超时
    - _interim_worker: 实时 interim，3s 超时，与 final 互不干扰
    """

    def __init__(
        self,
        model_name: str = "small",
        interim_model_name: str | None = None,
        language: str = "zh",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 0,
    ) -> None:
        self._model_name = model_name
        self._interim_model_name = interim_model_name or model_name
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._cpu_threads = cpu_threads if cpu_threads > 0 else max(1, mp.cpu_count() // 2)
        self._audio_buffer = bytearray()

        self._ctx = mp.get_context("spawn")

        # 最终转录 worker
        self._request_queue: mp.Queue | None = None
        self._result_queue: mp.Queue | None = None
        self._worker: mp.Process | None = None
        self._request_counter = 0

        # Interim 转录 worker（独立进程，互不阻塞）
        self._interim_request_queue: mp.Queue | None = None
        self._interim_result_queue: mp.Queue | None = None
        self._interim_worker: mp.Process | None = None
        self._interim_counter = 0

    def _start_worker(
        self,
        tag: str,
        model_name: str,
        cpu_threads: int,
    ) -> tuple[mp.Process, mp.Queue, mp.Queue]:
        """启动一个 STT worker 子进程。"""
        rq = self._ctx.Queue()
        sq = self._ctx.Queue()
        proc = self._ctx.Process(
            target=_stt_persistent_worker,
            args=(
                model_name,
                self._language,
                self._device,
                self._compute_type,
                cpu_threads,
                rq,
                sq,
                tag,
            ),
            daemon=True,
        )
        proc.start()
        logger.debug("STT %s subprocess started (pid=%d)", tag, proc.pid)
        return proc, rq, sq

    def start(self) -> None:
        """启动持久化 STT 子进程。"""
        if self._worker is not None:
            return
        self._worker, self._request_queue, self._result_queue = self._start_worker(
            "final",
            self._model_name,
            self._cpu_threads,
        )
        interim_threads = max(1, min(2, self._cpu_threads))
        self._interim_worker, self._interim_request_queue, self._interim_result_queue = (
            self._start_worker(
                "interim",
                self._interim_model_name,
                interim_threads,
            )
        )
        self._wait_worker_ready(self._result_queue, "final")
        self._wait_worker_ready(self._interim_result_queue, "interim")

    def _wait_worker_ready(self, result_queue: mp.Queue | None, tag: str, timeout: float = 20.0) -> None:
        """等待 worker 模型加载完成，避免首轮语音丢失 interim。"""
        if result_queue is None:
            return
        try:
            rid, status, _ = result_queue.get(timeout=timeout)
            if status != "ready":
                logger.warning("STT %s worker did not report ready (status=%s, rid=%s)", tag, status, rid)
        except Exception:
            logger.warning("STT %s worker ready timeout (%.0fs)", tag, timeout)

    def _stop_one(self, proc: mp.Process | None, rq: mp.Queue | None) -> None:
        """停止一个 worker 子进程。"""
        if proc is None:
            return
        if rq is not None:
            rq.put(None)
        proc.join(timeout=5)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=2)

    def stop(self) -> None:
        """停止 STT 子进程。"""
        self._stop_one(self._worker, self._request_queue)
        self._worker = None
        self._request_queue = None
        self._result_queue = None

        self._stop_one(self._interim_worker, self._interim_request_queue)
        self._interim_worker = None
        self._interim_request_queue = None
        self._interim_result_queue = None

        logger.info("STT subprocesses stopped")

    def _send_and_wait(
        self,
        request_queue: mp.Queue,
        result_queue: mp.Queue,
        audio_bytes: bytes,
        timeout: float,
        counter_attr: str,
        cancel: Any = None,
    ) -> str:
        """发送请求到指定 worker 并等待结果。"""
        import time as _time

        if not audio_bytes:
            return ""

        # 检查取消
        if cancel is not None and cancel.is_set():
            return ""

        # 递增计数器
        counter = getattr(self, counter_attr) + 1
        setattr(self, counter_attr, counter)

        audio_dur = len(audio_bytes) / (16000 * 2)

        # 清空旧结果
        while not result_queue.empty():
            try:
                result_queue.get_nowait()
            except Exception:
                break

        # 再次检查取消（清空队列可能耗时）
        if cancel is not None and cancel.is_set():
            return ""

        _t0 = _time.monotonic()
        request_queue.put((counter, audio_bytes))

        # 等待结果，支持取消
        result = None
        while True:
            if cancel is not None and cancel.is_set():
                return ""
            try:
                rid, status, result = result_queue.get(block=True, timeout=min(timeout, 0.5))
                break
            except Exception:
                # 超时 0.5s，检查取消后重试
                elapsed = _time.monotonic() - _t0
                if elapsed >= timeout:
                    if timeout < 10:
                        logger.debug("STT interim timeout (%.0fs)", timeout)
                    else:
                        logger.error("STT timeout (%.0fs)", timeout)
                    return ""

        _t1 = _time.monotonic()
        total_ms = (_t1 - _t0) * 1000

        if status == "ok":
            logger.debug(
                "STT #%d: audio=%.1fs, round-trip=%dms → '%s'",
                counter, audio_dur, total_ms, result[:30] if result else "",
            )
            return result
        else:
            logger.error("STT error: %s", result)
            return ""

    def transcribe_interim(self, audio_bytes: bytes, cancel: Any = None) -> str:
        """Interim 转录 — 使用独立的 interim worker，3s 超时。

        Args:
            audio_bytes: 16kHz 16bit PCM 音频数据
            cancel: threading.Event，设置后立即返回空字符串。
        """
        if not audio_bytes or len(audio_bytes) < 16000:
            return ""
        if self._interim_worker is None:
            return ""
        if cancel is not None and cancel.is_set():
            return ""
        return self._send_and_wait(
            self._interim_request_queue,
            self._interim_result_queue,
            audio_bytes,
            timeout=4.0,
            counter_attr="_interim_counter",
            cancel=cancel,
        )

    def _transcribe_final(self, audio_bytes: bytes) -> str:
        """最终转录 — 使用 final worker，30s 超时。"""
        if not audio_bytes:
            return ""
        if self._worker is None:
            return ""
        return self._send_and_wait(
            self._request_queue,
            self._result_queue,
            audio_bytes,
            timeout=30.0,
            counter_attr="_request_counter",
        )

    def transcribe_sync(self, audio_bytes: bytes) -> list[CleanedTextFrame]:
        """同步转录，返回 CleanedTextFrame 列表。用于测试。"""
        text = self._transcribe_final(audio_bytes)
        if text:
            return [CleanedTextFrame(text=text, raw_text=text)]
        return []

    def get_buffer_audio(self) -> bytes:
        """获取当前缓冲区的音频副本（不清空）。用于 interim 转录。"""
        return bytes(self._audio_buffer)

    def process_frame_sync(self, frame: Any) -> list:
        """同步处理帧，返回产生的帧列表。"""
        if isinstance(frame, VoiceStateFrame) and frame.state == "speech_end":
            audio = bytes(self._audio_buffer)
            self._audio_buffer = bytearray()
            text = self._transcribe_final(audio)
            if text:
                return [CleanedTextFrame(text=text, raw_text=text)]
            return []
        elif hasattr(frame, "audio"):
            self._audio_buffer.extend(frame.audio)
        return []

    def reset(self) -> None:
        """重置 STT 状态。"""
        self._audio_buffer.clear()
