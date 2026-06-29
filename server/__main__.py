"""Server 入口 — 可通过 python -m server 启动。"""

import argparse
import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv

load_dotenv()

# 配置日志
log_level = os.environ.get("BRIX_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from config.loader import load_config
from server.app import BrixServerApp
from server.transport import BrixServer
from server.daemon import ServerDaemon


def main() -> None:
    parser = argparse.ArgumentParser(description="Brix Server")
    parser.add_argument("--foreground", action="store_true", help="前台运行")
    parser.add_argument("--port", type=int, help="远程端口（可选）")
    args = parser.parse_args()

    config = load_config()
    daemon = ServerDaemon(
        pid_file=config.get("server", {}).get("pid_file", "~/.brix/server.pid")
    )

    # 检查是否已有 Server 运行
    if daemon.is_running():
        print("Server is already running")
        sys.exit(1)

    # 创建 Server 应用
    app = BrixServerApp(config)
    socket_path = config.get("server", {}).get("socket_path", "~/.brix/server.sock")

    # 创建事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 写入 PID 文件
    daemon.write_pid()

    # 防止 shutdown 被调用多次
    _shutdown_done = False

    async def shutdown() -> None:
        nonlocal _shutdown_done
        if _shutdown_done:
            return
        _shutdown_done = True
        await server.stop()
        await app.shutdown()
        daemon.cleanup()

    def _signal_handler(signum: int, frame: object) -> None:
        logger.info("Received signal %d, shutting down...", signum)
        # 使用 call_soon_threadsafe 确保在 event loop 线程中执行
        loop.call_soon_threadsafe(lambda: loop.create_task(shutdown()))

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # 启动 Server
    server = BrixServer(
        app=app,
        socket_path=socket_path,
        port=args.port,
    )
    loop.run_until_complete(server.start())

    print(f"✓ Server started. PID: {os.getpid()}")
    print(f"✓ Listening: unix://{server.socket_path}")
    if args.port:
        print(f"✓ Remote: ws://0.0.0.0:{args.port}")

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if not _shutdown_done:
            loop.run_until_complete(shutdown())
        loop.close()


if __name__ == "__main__":
    main()
