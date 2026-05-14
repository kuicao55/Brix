"""Entry point for the Brix CLI."""

import os
import logging

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# 配置日志：默认 WARNING，可通过环境变量 BRIX_LOG_LEVEL 覆盖
log_level = os.environ.get("BRIX_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.WARNING),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

import asyncio

from dotenv import load_dotenv

load_dotenv()

from cli.app import BrixCLI


def main() -> None:
    cli = BrixCLI()
    try:
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        cli._memory.save_session()


if __name__ == "__main__":
    main()
