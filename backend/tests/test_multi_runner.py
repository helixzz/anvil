"""Multi-runner support: TLS/token transport, scoped rescan, per-host lanes,
tune revert routing, and the /runners admin API."""
from __future__ import annotations

import asyncio
import hashlib
import ssl
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from anvil import db as anvil_db
from anvil.discovery import DiscoveredDevice
from anvil.models import LOCAL_RUNNER_ID, Device, Run, Runner, RunnerKind, RunStatus, TuneReceipt
from anvil.runner import RunnerClient, RunnerUnavailable, fetch_tls_fingerprint

runner_server = pytest.importorskip("anvil_runner.server")

TOKEN = "s3cret-runner-token-0123456789"


# ---------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def tls_material(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, str]:
    d = tmp_path_factory.mktemp("tls")
    cert, key = d / "tls.crt", d / "tls.key"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-subj", "/CN=anvil-runner-test", "-keyout", str(key), "-out", str(cert)],
        check=True, capture_output=True,
    )
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    return cert, key, hashlib.sha256(der).hexdigest()


@pytest_asyncio.fixture
async def tls_runner(tls_material: tuple[Path, Path, str]) -> AsyncIterator[tuple[str, str]]:
    """A real anvil-runner TCP+TLS listener on 127.0.0.1 (simulation mode)."""
    cert, key, fingerprint = tls_material
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(str(cert), str(key))
    servers = await runner_server.run_server(
        None, simulation=True, listen=("127.0.0.1", 0), ssl_context=ctx, token=TOKEN
    )
    port = servers[0].sockets[0].getsockname()[1]
    try:
        yield f"127.0.0.1:{port}", fingerprint
    finally:
        for s in servers:
            s.close()


async def _add(*objs: Any) -> None:
    async with anvil_db.session_scope() as session:
        for o in objs:
            session.add(o)


def _runner(rid: str, name: str | None = None) -> Runner:
    return Runner(
        id=rid, name=name or rid, kind=RunnerKind.TCP.value, address="10.0.0.1:9470",
        token=TOKEN, tls_fingerprint="ab" * 32, enabled=True,
    )


def _device(did: str, serial: str, runner_id: str) -> Device:
    disc = _discovered(serial)
    return Device(
        id=did, fingerprint=disc.fingerprint, model=disc.model, serial=serial,
        protocol="nvme", current_device_path=disc.path, runner_id=runner_id,
        is_testable=True, metadata_json={},
    )


def _discovered(serial: str, path: str = "/dev/nvme1n1") -> DiscoveredDevice:
    return DiscoveredDevice.from_dict({
        "path": path, "kname": path.rsplit("/", 1)[-1], "model": "TestDrive Gen5",
        "serial": serial, "size_bytes": 10**12, "protocol": "nvme", "is_testable": True,
    })


# ------------------------------------------------------- transport (TLS)


async def test_tls_runner_ping_with_token_and_pinned_cert(tls_runner: tuple[str, str]) -> None:
    address, fingerprint = tls_runner
    info = await RunnerClient(tcp_address=address, token=TOKEN, tls_fingerprint=fingerprint).ping_info()
    assert info is not None and info["ok"] is True
    assert info["host"]["hostname"]
    assert info["busy"] is False


async def test_tls_runner_rejects_wrong_token(tls_runner: tuple[str, str]) -> None:
    address, fingerprint = tls_runner
    client = RunnerClient(tcp_address=address, token="wrong-token-xxxxxxxxxx", tls_fingerprint=fingerprint)
    assert await client.ping_info() is None
    with pytest.raises(RuntimeError, match="unauthorized"):
        await client.discover()


async def test_tls_runner_rejects_fingerprint_mismatch(tls_runner: tuple[str, str]) -> None:
    address, _ = tls_runner
    client = RunnerClient(tcp_address=address, token=TOKEN, tls_fingerprint="00" * 32)
    assert await client.ping_info() is None
    with pytest.raises(RunnerUnavailable, match="fingerprint mismatch"):
        await client.discover()


async def test_fetch_tls_fingerprint_matches_certificate(tls_runner: tuple[str, str]) -> None:
    address, fingerprint = tls_runner
    assert await fetch_tls_fingerprint(address) == fingerprint


def test_remote_client_requires_fingerprint() -> None:
    with pytest.raises(ValueError):
        RunnerClient(tcp_address="10.0.0.1:9470", token=TOKEN)


async def test_runner_refuses_tcp_without_token() -> None:
    with pytest.raises(ValueError):
        await runner_server.run_server(None, listen=("127.0.0.1", 0), token=None)


# ---------------------------------------------------------- /runners API


async def test_register_remote_runner_pins_cert_and_hides_token(
    app_client: AsyncClient, tls_runner: tuple[str, str]
) -> None:
    address, fingerprint = tls_runner
    r = await app_client.post("/api/runners", json={"name": "gen5", "address": address, "token": TOKEN})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["tls_fingerprint"] == fingerprint
    assert body["online"] is True and body["has_token"] is True
    assert "token" not in body

    listed = (await app_client.get("/api/runners")).json()
    names = {x["name"]: x for x in listed}
    assert set(names) == {"local", "gen5"}
    assert names["gen5"]["online"] is True
    assert names["local"]["online"] is False  # no local socket in tests
    assert all("token" not in x for x in listed)

    status = (await app_client.get("/api/status")).json()
    assert {b["name"]: b["online"] for b in status["runners"]} == {"local": False, "gen5": True}
    assert status["runner_connected"] is False


async def test_register_rejects_bad_token(app_client: AsyncClient, tls_runner: tuple[str, str]) -> None:
    address, _ = tls_runner
    r = await app_client.post(
        "/api/runners", json={"name": "bad", "address": address, "token": "not-the-right-token"}
    )
    assert r.status_code == 400


async def test_local_runner_cannot_be_deleted(app_client: AsyncClient) -> None:
    await app_client.get("/api/runners")  # materialises the local row
    r = await app_client.delete(f"/api/runners/{LOCAL_RUNNER_ID}")
    assert r.status_code == 400


async def test_delete_runner_with_active_run_conflicts_then_detaches_devices(
    app_client: AsyncClient,
) -> None:
    await _add(_runner("r2"))
    await _add(_device("d1", "SER-1", "r2"))
    await _add(Run(id="run1", device_id="d1", profile_name="quick", profile_snapshot={},
                   status=RunStatus.QUEUED.value, device_path_at_run="/dev/nvme1n1", runner_id="r2"))
    assert (await app_client.delete("/api/runners/r2")).status_code == 409

    async with anvil_db.session_scope() as s:
        (await s.get(Run, "run1")).status = RunStatus.COMPLETE.value
    assert (await app_client.delete("/api/runners/r2")).status_code == 204
    async with anvil_db.session_scope() as s:
        d = await s.get(Device, "d1")
        assert d.runner_id is None and d.current_device_path is None and not d.is_testable


# ------------------------------------------------------ rescan scoping


@pytest.fixture
def fake_discover(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Per-runner discovery results; an Exception value simulates an unreachable host."""
    results: dict[str, Any] = {}

    async def _discover(runner_id: str | None = None) -> list[DiscoveredDevice]:
        value = results[runner_id or LOCAL_RUNNER_ID]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr("anvil.api.devices.discover", _discover)
    return results


async def test_rescan_one_host_never_marks_other_hosts_devices_missing(
    app_client: AsyncClient, fake_discover: dict[str, Any]
) -> None:
    await app_client.get("/api/runners")
    await _add(_runner("r2"))
    await _add(_device("dl", "SER-LOCAL", LOCAL_RUNNER_ID), _device("dr", "SER-REMOTE", "r2"))

    fake_discover["r2"] = []  # the remote drive was pulled
    r = await app_client.post("/api/devices/rescan", params={"runner_id": "r2"})
    assert r.status_code == 200, r.text
    by_id = {d["id"]: d for d in r.json()}
    assert by_id["dr"]["current_device_path"] is None
    assert by_id["dl"]["current_device_path"] == "/dev/nvme1n1"  # untouched
    assert by_id["dl"]["is_testable"] is True


async def test_rescan_all_tolerates_unreachable_host_and_moves_drive(
    app_client: AsyncClient, fake_discover: dict[str, Any]
) -> None:
    await app_client.get("/api/runners")
    await _add(_runner("r2"), _runner("r3"))
    await _add(_device("dl", "SER-LOCAL", LOCAL_RUNNER_ID), _device("d3", "SER-R3", "r3"))

    fake_discover[LOCAL_RUNNER_ID] = []
    fake_discover["r2"] = [_discovered("SER-LOCAL", "/dev/nvme5n1")]  # drive moved to r2
    fake_discover["r3"] = ConnectionRefusedError("down")

    r = await app_client.post("/api/devices/rescan")
    assert r.status_code == 200, r.text
    assert "r3" in r.headers["X-Anvil-Rescan-Errors"]
    by_id = {d["id"]: d for d in r.json()}
    assert by_id["dl"]["runner_id"] == "r2"
    assert by_id["dl"]["current_device_path"] == "/dev/nvme5n1"
    assert by_id["d3"]["current_device_path"] == "/dev/nvme1n1"  # unreachable host: kept


async def test_rescan_single_unreachable_host_is_503(
    app_client: AsyncClient, fake_discover: dict[str, Any]
) -> None:
    await _add(_runner("r2"))
    fake_discover["r2"] = ConnectionRefusedError("down")
    r = await app_client.post("/api/devices/rescan", params={"runner_id": "r2"})
    assert r.status_code == 503


async def test_new_run_is_pinned_to_device_runner(
    app_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    submitted: list[tuple[str, str | None]] = []

    class _Q:
        async def submit(self, run_id: str, runner_id: str | None = None) -> None:
            submitted.append((run_id, runner_id))

    monkeypatch.setattr("anvil.api.runs.get_queue", lambda: _Q())
    await _add(_runner("r2"))
    await _add(_device("dr", "SER-REMOTE", "r2"))
    r = await app_client.post("/api/runs", json={"device_id": "dr", "profile_name": "quick"})
    assert r.status_code == 201, r.text
    assert r.json()["runner_id"] == "r2"
    assert submitted == [(r.json()["id"], "r2")]


# ------------------------------------------------------ per-runner lanes


async def test_lanes_serialize_per_host_and_parallelize_across_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from anvil import orchestrator

    active: dict[str, int] = {}
    max_active: dict[str, int] = {}
    overlap_seen = asyncio.Event()
    done: list[str] = []

    async def fake_execute(run_id: str) -> None:
        host = run_id.split("-")[0]
        active[host] = active.get(host, 0) + 1
        max_active[host] = max(max_active.get(host, 0), active[host])
        if sum(active.values()) > 1:
            overlap_seen.set()
        await asyncio.sleep(0.05)
        active[host] -= 1
        done.append(run_id)

    monkeypatch.setattr(orchestrator, "_execute_run", fake_execute)
    q = orchestrator.JobQueue()
    q.start()
    try:
        for rid in ("a-1", "a-2", "a-3"):
            await q.submit(rid, "a")
        await q.submit("b-1", "b")
        for _ in range(100):
            if len(done) == 4:
                break
            await asyncio.sleep(0.01)
    finally:
        q.stop()
    assert sorted(done) == ["a-1", "a-2", "a-3", "b-1"]
    assert max_active == {"a": 1, "b": 1}  # one run at a time per host
    assert overlap_seen.is_set()  # but hosts ran concurrently
    assert [r for r in done if r.startswith("a")] == ["a-1", "a-2", "a-3"]


# --------------------------------------------------- tune revert routing


async def test_tune_revert_goes_to_the_runner_that_applied(
    app_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []

    class _Fake:
        def __init__(self, rid: str) -> None:
            self.rid = rid

        async def tune_apply(self, keys: list[str] | None) -> dict[str, Any]:
            calls.append(("apply", self.rid))
            return {"results": [{"key": "cpu_governor", "path": "/sys/x", "before": "a", "after": "b"}]}

        async def tune_revert(self, results: list[dict[str, Any]]) -> dict[str, Any]:
            calls.append(("revert", self.rid))
            return {"results": results}

    async def fake_get(runner_id: str | None = None) -> _Fake:
        return _Fake(runner_id or LOCAL_RUNNER_ID)

    monkeypatch.setattr("anvil.api.environment.get_runner_client", fake_get)
    await _add(_runner("r2"))

    r = await app_client.post("/api/environment/tune/apply", json={"runner_id": "r2"})
    assert r.status_code == 200, r.text
    receipt_id = r.json()["receipt_id"]
    async with anvil_db.session_scope() as s:
        assert (await s.get(TuneReceipt, receipt_id)).runner_id == "r2"

    r = await app_client.post("/api/environment/tune/revert", json={"receipt_id": receipt_id})
    assert r.status_code == 200, r.text
    assert calls == [("apply", "r2"), ("revert", "r2")]


# ------------------------------------------------- batch runs with repeat


@pytest.fixture
def captured_queue(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str | None]]:
    submitted: list[tuple[str, str | None]] = []

    class _Q:
        def __init__(self) -> None:
            self.running_run_ids: dict[str, str] = {}

        async def submit(self, run_id: str, runner_id: str | None = None) -> None:
            submitted.append((run_id, runner_id))

        async def abort(self, run_id: str) -> str:
            return "not_active"

    monkeypatch.setattr("anvil.api.runs.get_queue", lambda: _Q())
    return submitted


async def test_batch_repeat_creates_rounds_in_stable_order(
    app_client: AsyncClient, captured_queue: list[tuple[str, str | None]]
) -> None:
    await _add(_runner("r2"))
    devices = [_device(f"d{i:02d}", f"SER-{i:02d}", "r2") for i in range(24)]
    await _add(*devices)

    r = await app_client.post("/api/runs/batch", json={
        "device_ids": [d.id for d in devices], "profile_names": ["quick"], "repeat": 5,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 120 and body["skipped"] == [] and body["repeat"] == 5
    assert [rid for rid, _ in captured_queue] == body["run_ids"]
    assert {runner for _, runner in captured_queue} == {"r2"}

    async with anvil_db.session_scope() as s:
        runs = {r_.id: r_ for r_ in (await s.execute(select(Run))).scalars()}
    order = [runs[rid].device_id for rid in body["run_ids"]]
    # round-robin: all 24 drives once, then again, ... (not 5x the same drive in a row)
    assert order == [d.id for d in devices] * 5
    # DB order (used to rebuild the queue after a restart) matches submit order
    by_time = sorted(runs.values(), key=lambda x: x.queued_at)
    assert [x.id for x in by_time] == body["run_ids"]


async def test_batch_rejects_oversized_and_reports_skipped(
    app_client: AsyncClient, captured_queue: list[tuple[str, str | None]]
) -> None:
    await _add(_runner("r2"))
    await _add(_device("d1", "SER-1", "r2"))
    r = await app_client.post("/api/runs/batch", json={
        "device_ids": ["d1"], "profile_names": ["quick"], "repeat": 101,
    })
    assert r.status_code == 422
    r = await app_client.post("/api/runs/batch", json={
        "device_ids": [f"x{i}" for i in range(300)], "profile_names": ["quick"], "repeat": 7,
    })
    assert r.status_code == 400 and "limit" in r.json()["detail"]
    assert captured_queue == []

    r = await app_client.post("/api/runs/batch", json={
        "device_ids": ["d1", "d1", "ghost"], "profile_names": ["quick", "nope"], "repeat": 3,
    })
    body = r.json()
    assert body["created"] == 3  # duplicates collapsed, d1 x quick x 3
    assert sorted((s["device_id"], s["reason"]) for s in body["skipped"]) == [
        ("d1", "unknown profile"), ("ghost", "device not found"), ("ghost", "device not found"),
    ]


async def test_abort_cancels_a_queued_run_and_worker_skips_it(
    app_client: AsyncClient, captured_queue: list[tuple[str, str | None]]
) -> None:
    from anvil import orchestrator

    await _add(_runner("r2"))
    await _add(_device("d1", "SER-1", "r2"))
    run_id = (await app_client.post(
        "/api/runs", json={"device_id": "d1", "profile_name": "quick"}
    )).json()["id"]

    r = await app_client.post(f"/api/runs/{run_id}/abort")
    assert r.status_code == 200 and r.json()["result"] == "aborted_queued"
    # The lane worker reaching it later must not execute it (no runner is contacted).
    await orchestrator._execute_run(run_id)
    async with anvil_db.session_scope() as s:
        run = await s.get(Run, run_id)
        assert run.status == RunStatus.ABORTED.value and run.started_at is None
