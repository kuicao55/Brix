"""Entry point for the Brix CLI."""

import asyncio

from cli.app import BrixCLI


def main() -> None:
    cli = BrixCLI()
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()
