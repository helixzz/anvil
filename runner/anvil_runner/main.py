from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import click
import structlog

from anvil_runner.server import run_server


log = structlog.get_logger("anvil_runner")


def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@click.command()
@click.option("--socket", "socket_path", default="/run/anvil/runner.sock",
              type=click.Path(path_type=Path))
@click.option("--simulation/--no-simulation", default=False,
              help="Use fio's null ioengine instead of touching real devices.")
@click.option("--no-root-check", is_flag=True, help="Bypass the root-user requirement (dev only).")
def main(socket_path: Path, simulation: bool, no_root_check: bool) -> None:
    _configure_logging()
    if not no_root_check and os.geteuid() != 0:
        log.error("must_be_root")
        sys.exit(2)

    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()

    async def _main() -> None:
        log.info("runner_starting", socket=str(socket_path), simulation=simulation)
        server = await run_server(socket_path, simulation=simulation)
        os.chmod(socket_path, 0o660)
        loop = asyncio.get_running_loop()
        stop = loop.create_future()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: stop.set_result(None) if not stop.done() else None)
        try:
            await stop
        finally:
            server.close()
            await server.wait_closed()
            log.info("runner_stopped")

    asyncio.run(_main())


if __name__ == "__main__":
    main()
