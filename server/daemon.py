"""Server 进程管理 — PID 文件、信号处理。"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class ServerDaemon:
    """Server 进程管理。"""

    def __init__(self, pid_file: str = "~/.brix/server.pid") -> None:
        self._pid_file = Path(pid_file).expanduser()

    def write_pid(self) -> None:
        """写入 PID 文件。"""
        self._pid_file.parent.mkdir(parents=True, exist_ok=True)
        self._pid_file.write_text(str(os.getpid()))
        logger.info("PID file written: %s", self._pid_file)

    def read_pid(self) -> int | None:
        """读取 PID 文件。"""
        if not self._pid_file.exists():
            return None
        try:
            return int(self._pid_file.read_text().strip())
        except ValueError:
            return None

    def is_running(self) -> bool:
        """检查 Server 是否运行中。"""
        pid = self.read_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, 0)  # 检查进程是否存在
            return True
        except OSError:
            return False

    def cleanup(self) -> None:
        """清理 PID 文件。"""
        if self._pid_file.exists():
            self._pid_file.unlink()
            logger.info("PID file removed: %s", self._pid_file)

    def setup_signal_handlers(self, shutdown_callback: Callable[[], asyncio.coroutine]) -> None:
        """设置信号处理器。"""
        loop = asyncio.get_event_loop()

        def _handler(signum: int, frame: object) -> None:
            logger.info("Received signal %d, shutting down...", signum)
            loop.create_task(shutdown_callback())

        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)
