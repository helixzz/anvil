from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anvil.logging import get_logger

log = get_logger("anvil.rpc")


@dataclass
class RunnerEvent:
    run_id: str
    kind: str
    payload: dict[str, Any]


class RunnerClient:
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path
        self._lock = asyncio.Lock()

    async def ping(self) -> bool:
        try:
            reader, writer = await asyncio.open_unix_connection(str(self.socket_path))
        except (FileNotFoundError, ConnectionRefusedError, PermissionError):
            return False
        try:
            request = {"id": secrets.token_hex(8), "method": "ping", "params": {}}
            writer.write(json.dumps(request).encode() + b"\n")
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=3.0)
            response = json.loads(line or b"{}")
            return bool(response.get("result", {}).get("ok"))
        except (TimeoutError, json.JSONDecodeError):
            return False
        finally:
            await _close_writer(writer)

    async def discover(self) -> dict[str, Any]:
        return await self._call("discover", {})

    async def smart(self, device_path: str) -> dict[str, Any]:
        return await self._call("smart", {"device_path": device_path})

    async def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            reader, writer = await asyncio.open_unix_connection(str(self.socket_path))
            try:
                request = {"id": secrets.token_hex(8), "method": method, "params": params}
                writer.write(json.dumps(request).encode() + b"\n")
                await writer.drain()
                line = await asyncio.wait_for(reader.readline(), timeout=30.0)
                response = json.loads(line or b"{}")
                if "error" in response:
                    raise RuntimeError(response["error"])
                return response.get("result", {})
            finally:
                await _close_writer(writer)

    async def run_benchmark(
        self,
        run_id: str,
        device_path: str,
        profile: dict[str, Any],
    ) -> AsyncIterator[RunnerEvent]:
        reader, writer = await asyncio.open_unix_connection(str(self.socket_path))
        try:
            request = {
                "id": secrets.token_hex(8),
                "method": "run_benchmark",
                "params": {
                    "run_id": run_id,
                    "device_path": device_path,
                    "profile": profile,
                    "stream": True,
                },
            }
            writer.write(json.dumps(request).encode() + b"\n")
            await writer.drain()
            while not reader.at_eof():
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=3600.0)
                except TimeoutError:
                    log.warning("runner_read_timeout", run_id=run_id)
                    break
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = msg.get("event")
                payload = msg.get("payload", {})
                if not kind:
                    break
                yield RunnerEvent(run_id=run_id, kind=kind, payload=payload)
                if kind in {"run_complete", "run_failed", "run_aborted"}:
                    break
        finally:
            await _close_writer(writer)


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()


_client: RunnerClient | None = None


def get_runner_client(socket_path: Path) -> RunnerClient:
    global _client
    if _client is None or _client.socket_path != socket_path:
        _client = RunnerClient(socket_path)
    return _client
