from __future__ import annotations

import asyncio
import os
import signal
import ssl
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
@click.option("--socket", "socket_path", default=None, type=click.Path(path_type=Path),
              help="Unix socket for a co-located API (default /run/anvil/runner.sock "
                   "when --listen is not given).")
@click.option("--listen", default=None, metavar="HOST:PORT",
              help="Also serve remote APIs over TCP, e.g. 0.0.0.0:9470. Requires --token-file.")
@click.option("--tls-cert", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="PEM certificate for the TCP listener.")
@click.option("--tls-key", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="PEM private key for the TCP listener.")
@click.option("--token-file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="File containing the shared secret remote APIs must present.")
@click.option("--insecure-no-tls", is_flag=True,
              help="Allow --listen without TLS (testing only; token travels in clear).")
@click.option("--simulation/--no-simulation", default=False,
              help="Use fio's null ioengine instead of touching real devices.")
@click.option("--no-root-check", is_flag=True, help="Bypass the root-user requirement (dev only).")
def main(
    socket_path: Path | None,
    listen: str | None,
    tls_cert: Path | None,
    tls_key: Path | None,
    token_file: Path | None,
    insecure_no_tls: bool,
    simulation: bool,
    no_root_check: bool,
) -> None:
    _configure_logging()
    if not no_root_check and os.geteuid() != 0:
        log.error("must_be_root")
        sys.exit(2)

    if socket_path is None and listen is None:
        socket_path = Path("/run/anvil/runner.sock")

    listen_addr: tuple[str, int] | None = None
    ssl_context: ssl.SSLContext | None = None
    token: str | None = None
    if listen is not None:
        host, _, port = listen.rpartition(":")
        if not host or not port.isdigit():
            raise click.BadParameter("expected HOST:PORT", param_hint="--listen")
        listen_addr = (host.strip("[]"), int(port))
        if token_file is None:
            raise click.UsageError("--listen requires --token-file")
        token = token_file.read_text().strip()
        if len(token) < 16:
            raise click.UsageError("token must be at least 16 characters")
        if tls_cert and tls_key:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            ssl_context.load_cert_chain(certfile=str(tls_cert), keyfile=str(tls_key))
        elif not insecure_no_tls:
            raise click.UsageError("--listen requires --tls-cert/--tls-key (or --insecure-no-tls)")

    if socket_path is not None:
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        if socket_path.exists():
            socket_path.unlink()

    async def _main() -> None:
        log.info("runner_starting", socket=str(socket_path) if socket_path else None,
                 listen=listen, tls=ssl_context is not None, simulation=simulation)
        servers = await run_server(
            socket_path,
            simulation=simulation,
            listen=listen_addr,
            ssl_context=ssl_context,
            token=token,
        )
        if socket_path is not None:
            os.chmod(socket_path, 0o660)
        loop = asyncio.get_running_loop()
        stop = loop.create_future()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: stop.set_result(None) if not stop.done() else None)
        try:
            await stop
        finally:
            for server in servers:
                server.close()
                await server.wait_closed()
            log.info("runner_stopped")

    asyncio.run(_main())


if __name__ == "__main__":
    main()
