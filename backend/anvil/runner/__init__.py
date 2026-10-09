from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import secrets
import ssl
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anvil.logging import get_logger

log = get_logger("anvil.rpc")

CONNECT_TIMEOUT_S = 10.0


@dataclass
class RunnerEvent:
    run_id: str
    kind: str
    payload: dict[str, Any]


class RunnerStreamTruncated(RuntimeError):
    """Raised when the runner stream closes without a terminal event.

    A normal run ends with exactly one of `run_complete`, `run_failed`,
    or `run_aborted`. If the stream yields EOF, a read timeout, or an
    empty/unparseable message before that terminal event, the
    orchestrator must treat the run as failed and never mark it
    complete. Silencing this would be silent result corruption.
    """


class RunnerUnavailable(RuntimeError):
    """The runner could not be reached, rejected us, or failed TLS pinning."""


def normalize_fingerprint(value: str) -> str:
    """Accept `AB:CD:...`, `sha256 Fingerprint=AB:CD...` or bare hex."""
    value = value.strip()
    if "=" in value:
        value = value.split("=", 1)[1]
    return value.replace(":", "").replace(" ", "").lower()


def parse_tcp_address(address: str) -> tuple[str, int]:
    host, sep, port = address.strip().rpartition(":")
    if not sep or not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise ValueError(f"expected HOST:PORT, got {address!r}")
    return host.strip("[]"), int(port)


def _client_ssl_context() -> ssl.SSLContext:
    # Runners use self-signed certificates. Trust comes from pinning the
    # certificate's SHA-256 fingerprint after the handshake, not from a CA.
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _peer_fingerprint(writer: asyncio.StreamWriter) -> str | None:
    ssl_obj = writer.get_extra_info("ssl_object")
    if ssl_obj is None:
        return None
    der = ssl_obj.getpeercert(binary_form=True)
    if not der:
        return None
    return hashlib.sha256(der).hexdigest()


async def fetch_tls_fingerprint(address: str, timeout: float = CONNECT_TIMEOUT_S) -> str:
    """Connect once and return the runner certificate's SHA-256 (trust on first use)."""
    host, port = parse_tcp_address(address)
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=_client_ssl_context()), timeout=timeout
        )
    except (OSError, TimeoutError) as exc:
        raise RunnerUnavailable(f"cannot connect to {address}: {exc}") from exc
    try:
        fp = _peer_fingerprint(writer)
    finally:
        await _close_writer(writer)
    if not fp:
        raise RunnerUnavailable(f"{address} did not present a TLS certificate")
    return fp


class RunnerClient:
    """JSON-lines RPC client for one runner.

    Transport is either a unix socket (co-located runner, trusted by
    filesystem permissions) or TCP+TLS to a remote runner host, where the
    server certificate is pinned by SHA-256 and a shared token is sent with
    every request.
    """

    def __init__(
        self,
        socket_path: Path | None = None,
        *,
        tcp_address: str | None = None,
        token: str | None = None,
        tls_fingerprint: str | None = None,
        use_tls: bool = True,
    ):
        if (socket_path is None) == (tcp_address is None):
            raise ValueError("exactly one of socket_path / tcp_address is required")
        if tcp_address is not None and use_tls and not tls_fingerprint:
            raise ValueError("a TLS fingerprint is required for remote runners")
        self.socket_path = socket_path
        self.tcp_address = tcp_address
        self.token = token
        self.tls_fingerprint = normalize_fingerprint(tls_fingerprint) if tls_fingerprint else None
        self.use_tls = use_tls
        self._lock = asyncio.Lock()

    @property
    def cache_key(self) -> tuple[Any, ...]:
        return (self.socket_path, self.tcp_address, self.token, self.tls_fingerprint, self.use_tls)

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if self.socket_path is not None:
            return await asyncio.open_unix_connection(str(self.socket_path))
        assert self.tcp_address is not None
        host, port = parse_tcp_address(self.tcp_address)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host, port, ssl=_client_ssl_context() if self.use_tls else None
                ),
                timeout=CONNECT_TIMEOUT_S,
            )
        except TimeoutError as exc:
            raise RunnerUnavailable(f"timed out connecting to {self.tcp_address}") from exc
        if self.use_tls:
            actual = _peer_fingerprint(writer) or ""
            expected = self.tls_fingerprint or ""
            if not hmac.compare_digest(actual, expected):
                await _close_writer(writer)
                raise RunnerUnavailable(
                    f"TLS fingerprint mismatch for {self.tcp_address}: "
                    f"expected {expected}, got {actual}"
                )
        return reader, writer

    def _request(self, method: str, params: dict[str, Any]) -> bytes:
        request: dict[str, Any] = {"id": secrets.token_hex(8), "method": method, "params": params}
        if self.token:
            request["token"] = self.token
        return json.dumps(request).encode() + b"\n"

    async def ping_info(self) -> dict[str, Any] | None:
        """Return the runner's ping result (ok/simulation/busy/host), or None if down."""
        try:
            reader, writer = await self._open()
        except (OSError, RunnerUnavailable, ValueError):
            return None
        try:
            writer.write(self._request("ping", {}))
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            response = json.loads(line or b"{}")
            result = response.get("result") or {}
            return result if result.get("ok") else None
        except (TimeoutError, OSError, json.JSONDecodeError):
            return None
        finally:
            await _close_writer(writer)

    async def ping(self) -> bool:
        return await self.ping_info() is not None

    async def discover(self) -> dict[str, Any]:
        return await self._call("discover", {})

    async def smart(self, device_path: str) -> dict[str, Any]:
        return await self._call("smart", {"device_path": device_path})

    async def environment(self) -> dict[str, Any]:
        return await self._call("environment", {}, timeout=60.0)

    async def tune_preview(self, keys: list[str] | None = None) -> dict[str, Any]:
        return await self._call("tune_preview", {"keys": keys}, timeout=30.0)

    async def tune_apply(self, keys: list[str] | None = None) -> dict[str, Any]:
        return await self._call("tune_apply", {"keys": keys}, timeout=60.0)

    async def tune_revert(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._call("tune_revert", {"results": results}, timeout=60.0)

    async def _call(
        self, method: str, params: dict[str, Any], timeout: float = 30.0
    ) -> dict[str, Any]:
        async with self._lock:
            reader, writer = await self._open()
            try:
                writer.write(self._request(method, params))
                await writer.drain()
                line = await asyncio.wait_for(reader.readline(), timeout=timeout)
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
        reader, writer = await self._open()
        saw_terminal = False
        try:
            writer.write(self._request("run_benchmark", {
                "run_id": run_id,
                "device_path": device_path,
                "profile": profile,
                "stream": True,
            }))
            await writer.drain()
            while not reader.at_eof():
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=3600.0)
                except TimeoutError:
                    log.warning("runner_read_timeout", run_id=run_id)
                    raise RunnerStreamTruncated(
                        f"runner read timeout after 3600s with no terminal event for run {run_id}"
                    ) from None
                except OSError as exc:
                    raise RunnerStreamTruncated(
                        f"runner connection lost during run {run_id}: {exc}"
                    ) from exc
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = msg.get("event")
                payload = msg.get("payload", {})
                if not kind:
                    if msg.get("error"):
                        raise RuntimeError(f"runner rejected run {run_id}: {msg['error']}")
                    break
                yield RunnerEvent(run_id=run_id, kind=kind, payload=payload)
                if kind in {"run_complete", "run_failed", "run_aborted"}:
                    saw_terminal = True
                    break
        finally:
            await _close_writer(writer)
        if not saw_terminal:
            raise RunnerStreamTruncated(
                f"runner stream closed before emitting a terminal event for run {run_id}"
            )


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()
