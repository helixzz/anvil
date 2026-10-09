"""Resolve runner ids to RPC clients.

The `local` runner is the co-located container reached through
`ANVIL_RUNNER_SOCKET`; the environment variable always wins over whatever
address is stored in its row so existing deployments keep working.
Remote runners are `tcp` rows (TLS-pinned, token-authenticated).
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from anvil.config import get_settings
from anvil.db import session_scope
from anvil.models import LOCAL_RUNNER_ID, Runner, RunnerKind
from anvil.runner import RunnerClient, RunnerUnavailable

_clients: dict[str, RunnerClient] = {}


class RunnerNotFound(LookupError):
    pass


def _build_client(runner: Runner) -> RunnerClient:
    if runner.kind == RunnerKind.UNIX.value:
        path = get_settings().runner_socket if runner.id == LOCAL_RUNNER_ID else Path(runner.address)
        return RunnerClient(path)
    if runner.kind == RunnerKind.TCP.value:
        return RunnerClient(
            tcp_address=runner.address,
            token=runner.token,
            tls_fingerprint=runner.tls_fingerprint,
        )
    raise RunnerUnavailable(f"runner {runner.name}: unknown kind {runner.kind!r}")


def client_for(runner: Runner) -> RunnerClient:
    """Return a cached client for this row, rebuilding it if the connection settings changed."""
    fresh = _build_client(runner)
    cached = _clients.get(runner.id)
    if cached is not None and cached.cache_key == fresh.cache_key:
        return cached
    _clients[runner.id] = fresh
    return fresh


def local_client() -> RunnerClient:
    """Client for the co-located runner, without touching the database."""
    path = get_settings().runner_socket
    cached = _clients.get(LOCAL_RUNNER_ID)
    if cached is not None and cached.socket_path == path:
        return cached
    client = RunnerClient(path)
    _clients[LOCAL_RUNNER_ID] = client
    return client


async def ensure_local_runner(session: AsyncSession) -> Runner:
    """Make sure the `local` row exists (fresh installs, tests) and return it."""
    runner = await session.get(Runner, LOCAL_RUNNER_ID)
    if runner is None:
        runner = Runner(
            id=LOCAL_RUNNER_ID,
            name="local",
            kind=RunnerKind.UNIX.value,
            address=str(get_settings().runner_socket),
            enabled=True,
        )
        session.add(runner)
        await session.flush()
    return runner


async def get_runner_client(runner_id: str | None = LOCAL_RUNNER_ID) -> RunnerClient:
    """Resolve a runner id (None = local) to a client. Raises RunnerNotFound / RunnerUnavailable."""
    runner_id = runner_id or LOCAL_RUNNER_ID
    async with session_scope() as session:
        runner = await session.get(Runner, runner_id)
        if runner is None:
            if runner_id == LOCAL_RUNNER_ID:
                return local_client()
            raise RunnerNotFound(f"runner {runner_id} not found")
        if not runner.enabled:
            raise RunnerUnavailable(f"runner {runner.name} is disabled")
        return client_for(runner)


async def record_ping(runner_id: str, info: dict[str, Any] | None) -> None:
    """Persist liveness + host facts from a successful ping."""
    if info is None:
        return
    async with session_scope() as session:
        runner = await session.get(Runner, runner_id)
        if runner is None:
            return
        runner.last_seen_at = datetime.now(UTC)
        if info.get("host"):
            runner.host_info = info["host"]
