"""Entry point for the Brix CLI."""

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

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
