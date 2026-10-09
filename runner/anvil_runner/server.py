from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
import platform
import socket
import ssl
from pathlib import Path
from typing import Any

import structlog

from anvil_runner import __version__
from anvil_runner.devices import lsblk_json, nvme_list, nvme_smart, read_smart, smartctl_all
from anvil_runner.discovery import discover as discover_devices
from anvil_runner.env import environment_report
from anvil_runner.env_tune import apply as tune_apply, preview as tune_preview, revert as tune_revert
from anvil_runner.fio import FioRunner, PhaseRequest


log = structlog.get_logger("anvil_runner.server")

SMART_POLL_INTERVAL_S = 5.0
THERMAL_ABORT_THRESHOLD_C = 75
THERMAL_ABORT_CONSECUTIVE = 6


def host_info() -> dict[str, Any]:
    """Describe the machine this runner executes on.

    Reported through `ping` so the API records the *test host's* platform on
    each run (not the API container's), and so operators can tell runner
    hosts apart in the UI.
    """
    info: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "runner_version": __version__,
        "cpu_count": os.cpu_count(),
    }
    with contextlib.suppress(OSError):
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                info["cpu_model"] = line.split(":", 1)[1].strip()
                break
    with contextlib.suppress(OSError, ValueError, IndexError):
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                info["mem_total_bytes"] = int(line.split()[1]) * 1024
                break
    return info


async def run_server(
    socket_path: Path | None,
    simulation: bool = False,
    *,
    listen: tuple[str, int] | None = None,
    ssl_context: ssl.SSLContext | None = None,
    token: str | None = None,
) -> list[asyncio.AbstractServer]:
    """Start the RPC listeners.

    - `socket_path`: local unix socket (trusted via filesystem permissions,
      no token). Used by the co-located API container.
    - `listen`: TCP `(host, port)` for remote APIs. Requires `token`; every
      request must carry it. `ssl_context` should always be set in
      production — the API pins the certificate's SHA-256 fingerprint.
    """
    if listen is not None and not token:
        raise ValueError("a token is required when listening on TCP")
    runner = FioRunner(simulation=simulation)
    bench_lock = asyncio.Lock()
    servers: list[asyncio.AbstractServer] = []
    if socket_path is not None:
        servers.append(await asyncio.start_unix_server(
            _make_handler(runner, bench_lock, simulation, required_token=None),
            path=str(socket_path),
        ))
    if listen is not None:
        servers.append(await asyncio.start_server(
            _make_handler(runner, bench_lock, simulation, required_token=token),
            host=listen[0],
            port=listen[1],
            ssl=ssl_context,
        ))
    return servers


def _make_handler(
    runner: FioRunner,
    bench_lock: asyncio.Lock,
    simulation: bool,
    required_token: str | None,
) -> Any:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await reader.readline()
            if not line:
                return
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                writer.write(json.dumps({"error": f"bad json: {exc}"}).encode() + b"\n")
                await writer.drain()
                return

            method = request.get("method")
            params = request.get("params") or {}
            req_id = request.get("id")

            if required_token is not None:
                supplied = request.get("token")
                if not isinstance(supplied, str) or not hmac.compare_digest(
                    supplied.encode(), required_token.encode()
                ):
                    peer = writer.get_extra_info("peername")
                    log.warning("rpc_unauthorized", method=method, peer=str(peer))
                    writer.write(json.dumps(
                        {"id": req_id, "error": "unauthorized"}
                    ).encode() + b"\n")
                    await writer.drain()
                    return

            log.info("rpc_call", method=method, id=req_id)

            if method == "ping":
                writer.write(json.dumps({"id": req_id, "result": {
                    "ok": True,
                    "simulation": simulation,
                    "busy": bench_lock.locked(),
                    "host": host_info(),
                }}).encode() + b"\n")
                await writer.drain()
                return

            if method == "discover":
                devices = await discover_devices()
                result = {
                    "devices": [d.as_dict() for d in devices],
                    "nvme_list": await nvme_list(),
                    "lsblk": await lsblk_json(),
                }
                writer.write(json.dumps({"id": req_id, "result": result}).encode() + b"\n")
                await writer.drain()
                return

            if method == "smart":
                device_path = params.get("device_path")
                if not device_path:
                    writer.write(json.dumps(
                        {"id": req_id, "error": "missing device_path"}
                    ).encode() + b"\n")
                    await writer.drain()
                    return
                result = await read_smart(device_path)
                writer.write(json.dumps({"id": req_id, "result": result}).encode() + b"\n")
                await writer.drain()
                return

            if method == "environment":
                checks = await environment_report()
                writer.write(json.dumps(
                    {"id": req_id, "result": {"checks": checks}}
                ).encode() + b"\n")
                await writer.drain()
                return

            if method == "tune_preview":
                keys = params.get("keys") or None
                result = tune_preview(keys)
                writer.write(json.dumps({"id": req_id, "result": {"preview": result}}).encode() + b"\n")
                await writer.drain()
                return

            if method == "tune_apply":
                keys = params.get("keys") or None
                receipt = tune_apply(keys)
                writer.write(json.dumps({"id": req_id, "result": receipt.as_dict()}).encode() + b"\n")
                await writer.drain()
                return

            if method == "tune_revert":
                receipt_results = params.get("results") or []
                receipt = tune_revert(receipt_results)
                writer.write(json.dumps({"id": req_id, "result": receipt.as_dict()}).encode() + b"\n")
                await writer.drain()
                return

            if method == "run_benchmark":
                if bench_lock.locked():
                    writer.write(json.dumps({"event": "run_failed", "payload": {
                        "error": "runner busy: another benchmark is already running on this host",
                    }}).encode() + b"\n")
                    await writer.drain()
                    return
                async with bench_lock:
                    await _run_benchmark_stream(runner, params, writer)
                return

            writer.write(json.dumps(
                {"id": req_id, "error": f"unknown method: {method}"}
            ).encode() + b"\n")
            await writer.drain()
        except Exception as exc:  # pragma: no cover - defensive
            log.error("rpc_error", error=str(exc), exc_info=True)
            with contextlib.suppress(Exception):
                writer.write(json.dumps({"error": str(exc)}).encode() + b"\n")
                await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    return handle


async def _run_benchmark_stream(
    runner: FioRunner,
    params: dict[str, Any],
    writer: asyncio.StreamWriter,
) -> None:
    run_id = params["run_id"]
    device_path = params["device_path"]
    profile = params["profile"]
    phases_raw = profile.get("phases") or []

    write_lock = asyncio.Lock()

    async def emit(event: dict[str, Any]) -> None:
        async with write_lock:
            writer.write(json.dumps(event).encode() + b"\n")
            await writer.drain()

    stop_smart = asyncio.Event()
    thermal_abort = asyncio.Event()
    smart_task = asyncio.create_task(
        _smart_poller(device_path, emit, stop_smart, thermal_abort),
        name=f"smart-poller-{run_id}",
    )

    current_phase_task: asyncio.Task[None] | None = None

    async def _abort_on_thermal() -> None:
        await thermal_abort.wait()
        log.warning("thermal_abort_triggered", device=device_path)
        await emit({
            "event": "thermal_abort_armed",
            "payload": {
                "device_path": device_path,
                "threshold_c": THERMAL_ABORT_THRESHOLD_C,
            },
        })
        if current_phase_task is not None and not current_phase_task.done():
            current_phase_task.cancel()

    thermal_task = asyncio.create_task(_abort_on_thermal(), name=f"thermal-watch-{run_id}")

    try:
        for phase_spec in phases_raw:
            if thermal_abort.is_set():
                break
            phase = PhaseRequest(
                name=phase_spec["name"],
                pattern=phase_spec["pattern"],
                block_size=int(phase_spec["block_size"]),
                iodepth=int(phase_spec["iodepth"]),
                numjobs=int(phase_spec["numjobs"]),
                runtime_s=int(phase_spec["runtime_s"]),
                ramp_time_s=int(phase_spec.get("ramp_time_s", 2)),
                rwmix_write_pct=int(phase_spec.get("rwmix_write_pct", 0)),
                offset_bytes=int(phase_spec.get("offset_bytes") or 0),
                size_bytes=int(phase_spec["size_bytes"]) if phase_spec.get("size_bytes") else None,
                read_only=bool(phase_spec.get("read_only", False)),
            )

            async def _drain_phase() -> None:
                # aclosing: if emit() fails because the API connection
                # dropped, the generator is closed right away and fio is
                # terminated instead of running on unobserved.
                async with contextlib.aclosing(
                    runner.run_phase(run_id, device_path, phase)
                ) as events:
                    async for event in events:
                        await emit(event)
                        if event["event"] == "phase_failed":
                            await emit({
                                "event": "run_failed",
                                "payload": {"error": event["payload"].get("error") or "phase failed"},
                            })
                            raise _PhaseFailure()

            current_phase_task = asyncio.create_task(_drain_phase())
            try:
                await current_phase_task
            except asyncio.CancelledError:
                # Thermal abort tripped while the phase was running.
                if thermal_abort.is_set():
                    await emit({
                        "event": "run_aborted",
                        "payload": {
                            "reason": "thermal_abort",
                            "threshold_c": THERMAL_ABORT_THRESHOLD_C,
                            "consecutive_samples_required": THERMAL_ABORT_CONSECUTIVE,
                        },
                    })
                    return
                raise
            except _PhaseFailure:
                return

        if thermal_abort.is_set():
            await emit({
                "event": "run_aborted",
                "payload": {
                    "reason": "thermal_abort",
                    "threshold_c": THERMAL_ABORT_THRESHOLD_C,
                    "consecutive_samples_required": THERMAL_ABORT_CONSECUTIVE,
                },
            })
            return
        await emit({"event": "run_complete", "payload": {"run_id": run_id}})
    finally:
        stop_smart.set()
        thermal_abort.set()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(smart_task, timeout=5.0)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(thermal_task, timeout=2.0)


class _PhaseFailure(Exception):
    pass


async def _smart_poller(
    device_path: str,
    emit: Any,
    stop_event: asyncio.Event,
    thermal_abort: asyncio.Event | None = None,
) -> None:
    """Emit a smart_sample event every SMART_POLL_INTERVAL_S seconds for the run."""
    is_nvme = device_path.startswith("/dev/nvme")
    consecutive_overheat = 0
    while not stop_event.is_set():
        try:
            sample = await _read_smart_sample(device_path, is_nvme)
            if sample:
                await emit({"event": "smart_sample", "payload": sample})
                temp_c = sample.get("temperature_c")
                if (
                    thermal_abort is not None
                    and isinstance(temp_c, (int, float))
                    and temp_c >= THERMAL_ABORT_THRESHOLD_C
                ):
                    consecutive_overheat += 1
                    if consecutive_overheat >= THERMAL_ABORT_CONSECUTIVE:
                        thermal_abort.set()
                        return
                else:
                    consecutive_overheat = 0
        except Exception as exc:
            log.warning("smart_poll_failed", device=device_path, error=str(exc))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SMART_POLL_INTERVAL_S)
        except asyncio.TimeoutError:
            continue


async def _read_smart_sample(device_path: str, is_nvme: bool) -> dict[str, Any] | None:
    if is_nvme:
        data = await nvme_smart(device_path)
        if data.get("error"):
            return None
        temp_k = data.get("temperature")
        if temp_k is None:
            return None
        sample: dict[str, Any] = {
            "device_path": device_path,
            "temperature_c": int(temp_k) - 273,
            "critical_warning": data.get("critical_warning"),
            "percent_used": data.get("percent_used"),
            "power_on_hours": data.get("power_on_hours"),
            "media_errors": data.get("media_errors"),
            "num_err_log_entries": data.get("num_err_log_entries"),
        }
        return sample
    data = await smartctl_all(device_path)
    if data.get("error"):
        return None
    temp = (data.get("temperature") or {}).get("current")
    if temp is None:
        return None
    return {"device_path": device_path, "temperature_c": int(temp)}
