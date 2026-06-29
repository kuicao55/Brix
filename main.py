"""Entry point for the Brix CLI."""

import os
import sys
import asyncio
import subprocess
import signal
import time
import logging
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# 配置日志：默认 WARNING，可通过环境变量 BRIX_LOG_LEVEL 覆盖
log_level = os.environ.get("BRIX_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.WARNING),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from dotenv import load_dotenv

load_dotenv()

from config.loader import load_config
from server.daemon import ServerDaemon


def cmd_serve(foreground: bool = False, port: int | None = None) -> None:
    """启动 Server。"""
    args = [sys.executable, "-m", "server"]
    if foreground:
        args.append("--foreground")
    if port:
        args.extend(["--port", str(port)])

    if foreground:
        # 前台运行
        os.execvp(sys.executable, args)
    else:
        # 后台启动
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # 脱离当前终端
        )
        # 等待 Server 就绪
        config = load_config()
        daemon = ServerDaemon(
            pid_file=config.get("server", {}).get("pid_file", "~/.brix/server.pid")
        )
        for _ in range(50):  # 最多等待 5 秒
            if daemon.is_running():
                print(f"✓ Server started. PID: {daemon.read_pid()}")
                return
            time.sleep(0.1)
        print("✗ Server failed to start")
        sys.exit(1)


def cmd_stop() -> None:
    """停止 Server。"""
    config = load_config()
    daemon = ServerDaemon(
        pid_file=config.get("server", {}).get("pid_file", "~/.brix/server.pid")
    )
    pid = daemon.read_pid()
    if pid is None:
        print("Server is not running")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        # 等待进程退出
        for _ in range(50):
            if not daemon.is_running():
                print("✓ Server stopped")
                return
            time.sleep(0.1)
        # 强制终止
        os.kill(pid, signal.SIGKILL)
        print("✓ Server force stopped")
    except OSError:
        print("Server is not running")
    daemon.cleanup()


def cmd_status() -> None:
    """查询 Server 状态。"""
    config = load_config()
    daemon = ServerDaemon(
        pid_file=config.get("server", {}).get("pid_file", "~/.brix/server.pid")
    )
    pid = daemon.read_pid()
    if pid is None or not daemon.is_running():
        print("Server: ● not running")
        return

    # TODO: 通过 WebSocket 查询详细状态
    print(f"Server: ● running (PID: {pid})")


def cmd_tui(remote: str | None = None) -> None:
    """启动 TUI（自动检测/启动 Server）。"""
    config = load_config()
    daemon = ServerDaemon(
        pid_file=config.get("server", {}).get("pid_file", "~/.brix/server.pid")
    )

    # 检查 Server 是否运行
    if not daemon.is_running():
        print("Starting server...")
        cmd_serve(foreground=False)

    # 启动 TUI Client
    from cli.app import BrixTUIClient

    client = BrixTUIClient(remote=remote)
    asyncio.run(client.run())


def main() -> None:
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "serve":
            import argparse

            parser = argparse.ArgumentParser()
            parser.add_argument("--foreground", action="store_true")
            parser.add_argument("--port", type=int)
            args = parser.parse_args(sys.argv[2:])
            cmd_serve(args.foreground, args.port)
        elif cmd == "stop":
            cmd_stop()
        elif cmd == "status":
            cmd_status()
        elif cmd == "--remote":
            cmd_tui(remote=sys.argv[2] if len(sys.argv) > 2 else None)
        else:
            print(f"Unknown command: {cmd}")
            sys.exit(1)
    else:
        # 默认：启动 TUI
        cmd_tui()


if __name__ == "__main__":
    main()
