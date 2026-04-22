from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import structlog

from anvil_runner.devices import lsblk_json, nvme_list, read_smart
from anvil_runner.fio import FioRunner, PhaseRequest


log = structlog.get_logger("anvil_runner.server")


async def run_server(socket_path: Path, simulation: bool = False) -> asyncio.AbstractServer:
    runner = FioRunner(simulation=simulation)

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

            log.info("rpc_call", method=method, id=req_id)

            if method == "ping":
                writer.write(json.dumps(
                    {"id": req_id, "result": {"ok": True, "simulation": simulation}}
                ).encode() + b"\n")
                await writer.drain()
                return

            if method == "discover":
                result = {
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

            if method == "run_benchmark":
                await _run_benchmark_stream(runner, params, writer)
                return

            writer.write(json.dumps(
                {"id": req_id, "error": f"unknown method: {method}"}
            ).encode() + b"\n")
            await writer.drain()
        except Exception as exc:  # pragma: no cover - defensive
            log.error("rpc_error", error=str(exc), exc_info=True)
            try:
                writer.write(json.dumps({"error": str(exc)}).encode() + b"\n")
                await writer.drain()
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_unix_server(handle, path=str(socket_path))
    return server


async def _run_benchmark_stream(
    runner: FioRunner,
    params: dict[str, Any],
    writer: asyncio.StreamWriter,
) -> None:
    run_id = params["run_id"]
    device_path = params["device_path"]
    profile = params["profile"]
    phases_raw = profile.get("phases") or []

    for phase_spec in phases_raw:
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
        async for event in runner.run_phase(run_id, device_path, phase):
            writer.write(json.dumps(event).encode() + b"\n")
            await writer.drain()
            if event["event"] == "phase_failed":
                writer.write(json.dumps({
                    "event": "run_failed",
                    "payload": {"error": event["payload"].get("error") or "phase failed"},
                }).encode() + b"\n")
                await writer.drain()
                return

    writer.write(json.dumps({"event": "run_complete", "payload": {"run_id": run_id}}).encode() + b"\n")
    await writer.drain()
