from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from anvil.runner import RunnerClient, RunnerStreamTruncated


class _FakeServer:
    """Minimal unix-socket server that scripts a response sequence.

    Tests hand it a list of line-strings to emit after reading the
    request, then whether to close cleanly or hold the connection open
    for the read-timeout path.
    """

    def __init__(self, lines: list[str], sleep_before_close: float = 0.0) -> None:
        self.lines = lines
        self.sleep_before_close = sleep_before_close
        self.server: asyncio.base_events.Server | None = None

    async def start(self, socket_path: Path) -> None:
        async def handler(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            await reader.readline()
            for line in self.lines:
                writer.write((line + "\n").encode())
                await writer.drain()
            if self.sleep_before_close:
                await asyncio.sleep(self.sleep_before_close)
            writer.close()

        self.server = await asyncio.start_unix_server(handler, path=str(socket_path))

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()


@pytest.fixture
def socket_path(tmp_path: Path) -> Path:
    p = tmp_path / "runner.sock"
    return p


async def test_run_benchmark_accepts_run_complete(socket_path: Path) -> None:
    srv = _FakeServer([
        json.dumps({"event": "phase_started", "payload": {"phase_name": "p1"}}),
        json.dumps({"event": "run_complete", "payload": {"run_id": "r1"}}),
    ])
    await srv.start(socket_path)
    try:
        client = RunnerClient(socket_path)
        events = []
        async for ev in client.run_benchmark(run_id="r1", device_path="/dev/x", profile={}):
            events.append(ev.kind)
        assert events == ["phase_started", "run_complete"]
    finally:
        await srv.stop()


async def test_run_benchmark_raises_on_missing_terminal(socket_path: Path) -> None:
    srv = _FakeServer([
        json.dumps({"event": "phase_started", "payload": {"phase_name": "p1"}}),
        json.dumps({"event": "phase_sample", "payload": {"read_iops": 1000}}),
    ])
    await srv.start(socket_path)
    try:
        client = RunnerClient(socket_path)
        collected: list[str] = []
        with pytest.raises(RunnerStreamTruncated):
            async for ev in client.run_benchmark(run_id="r1", device_path="/dev/x", profile={}):
                collected.append(ev.kind)
        assert collected == ["phase_started", "phase_sample"]
    finally:
        await srv.stop()


async def test_run_benchmark_raises_on_immediate_eof(socket_path: Path) -> None:
    srv = _FakeServer([])
    await srv.start(socket_path)
    try:
        client = RunnerClient(socket_path)
        with pytest.raises(RunnerStreamTruncated):
            async for _ev in client.run_benchmark(run_id="r1", device_path="/dev/x", profile={}):
                pass
    finally:
        await srv.stop()


async def test_run_benchmark_accepts_run_failed_as_terminal(socket_path: Path) -> None:
    srv = _FakeServer([
        json.dumps({"event": "run_failed", "payload": {"error": "fio exit 1"}}),
    ])
    await srv.start(socket_path)
    try:
        client = RunnerClient(socket_path)
        events = []
        async for ev in client.run_benchmark(run_id="r1", device_path="/dev/x", profile={}):
            events.append(ev.kind)
        assert events == ["run_failed"]
    finally:
        await srv.stop()


async def test_run_benchmark_accepts_run_aborted_as_terminal(socket_path: Path) -> None:
    srv = _FakeServer([
        json.dumps({"event": "run_aborted", "payload": {"reason": "thermal_abort"}}),
    ])
    await srv.start(socket_path)
    try:
        client = RunnerClient(socket_path)
        events = []
        async for ev in client.run_benchmark(run_id="r1", device_path="/dev/x", profile={}):
            events.append(ev.kind)
        assert events == ["run_aborted"]
    finally:
        await srv.stop()
