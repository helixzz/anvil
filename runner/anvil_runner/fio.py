from __future__ import annotations

import asyncio
import json
import os
import signal
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Template


FIO_JOB_TEMPLATE = Template("""
[global]
ioengine={{ ioengine }}
direct=1
thread=1
time_based=1
runtime={{ runtime_s }}
ramp_time={{ ramp_s }}
randrepeat=0
norandommap=1
group_reporting=1
filename={{ device }}
{% if offset_bytes %}offset={{ offset_bytes }}
{% endif %}{% if size_bytes %}size={{ size_bytes }}
{% endif %}percentile_list=50:95:99:99.5:99.9:99.99

[{{ job_name }}]
rw={{ pattern }}
bs={{ block_size }}
iodepth={{ iodepth }}
numjobs={{ numjobs }}
{% if rwmix_write_pct %}rwmixwrite={{ rwmix_write_pct }}
{% endif %}
""")


PERCENTILE_MAP = {
    "p50": "50.000000",
    "p95": "95.000000",
    "p99": "99.000000",
    "p995": "99.500000",
    "p999": "99.900000",
    "p9999": "99.990000",
}


@dataclass
class PhaseRequest:
    name: str
    pattern: str
    block_size: int
    iodepth: int
    numjobs: int
    runtime_s: int
    ramp_time_s: int
    rwmix_write_pct: int
    offset_bytes: int
    size_bytes: int | None
    read_only: bool


@dataclass
class FioRunner:
    simulation: bool = False
    fio_binary: str = "fio"
    workdir: Path = field(default_factory=lambda: Path(tempfile.gettempdir()) / "anvil")

    def __post_init__(self) -> None:
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _render_jobfile(self, device: str, phase: PhaseRequest) -> str:
        ioengine = "null" if self.simulation else "io_uring"
        return FIO_JOB_TEMPLATE.render(
            ioengine=ioengine,
            device="/dev/null" if self.simulation else device,
            runtime_s=phase.runtime_s,
            ramp_s=phase.ramp_time_s,
            offset_bytes=phase.offset_bytes or 0,
            size_bytes=phase.size_bytes or 0,
            job_name=phase.name,
            pattern=phase.pattern,
            block_size=phase.block_size,
            iodepth=phase.iodepth,
            numjobs=phase.numjobs,
            rwmix_write_pct=phase.rwmix_write_pct,
        )

    async def run_phase(
        self, run_id: str, device: str, phase: PhaseRequest
    ) -> AsyncIterator[dict[str, Any]]:
        jobfile = self._render_jobfile(device, phase)
        job_path = self.workdir / f"{run_id}.{phase.name}.fio"
        job_path.write_text(jobfile)

        yield {"event": "phase_started", "payload": {
            "phase_name": phase.name,
            "jobfile": jobfile,
            "expected_runtime_s": phase.runtime_s + phase.ramp_time_s,
        }}

        cmd = [
            self.fio_binary,
            "--output-format=json+",
            "--status-interval=1",
            str(job_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid,
        )

        assert proc.stdout is not None
        stderr_task = asyncio.create_task(_drain(proc.stderr))

        buffer: list[str] = []
        stdout_all: list[str] = []
        depth = 0
        seen_open = False

        try:
            while not proc.stdout.at_eof():
                try:
                    chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                if not chunk:
                    break
                text = chunk.decode(errors="replace")
                stdout_all.append(text)
                for ch in text:
                    if ch == "{":
                        if depth == 0:
                            buffer = []
                            seen_open = True
                        depth += 1
                    if seen_open:
                        buffer.append(ch)
                    if ch == "}" and depth > 0:
                        depth -= 1
                        if depth == 0 and seen_open:
                            raw = "".join(buffer).strip()
                            buffer = []
                            seen_open = False
                            try:
                                snapshot = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            sample = _snapshot_to_sample(phase.name, snapshot)
                            if sample:
                                yield {"event": "phase_sample", "payload": sample}

            rc = await proc.wait()
        except asyncio.CancelledError:
            _terminate(proc)
            await stderr_task
            raise

        await stderr_task
        stderr_output = stderr_task.result()

        if rc != 0:
            yield {"event": "phase_failed", "payload": {
                "phase_name": phase.name,
                "returncode": rc,
                "stderr": stderr_output[-2000:],
            }}
            return

        fio_result = _parse_last_json_object("".join(stdout_all))
        if fio_result is None:
            yield {"event": "phase_failed", "payload": {
                "phase_name": phase.name,
                "error": "fio produced no parseable JSON on stdout",
            }}
            return

        summary = _summarise(fio_result)
        yield {"event": "phase_complete", "payload": {
            "phase_name": phase.name,
            "summary": summary,
            "fio_result": fio_result,
        }}


async def _drain(stream: asyncio.StreamReader | None) -> str:
    if stream is None:
        return ""
    chunks = []
    while True:
        data = await stream.read(4096)
        if not data:
            return "".join(chunks)
        chunks.append(data.decode(errors="replace"))


def _parse_last_json_object(text: str) -> dict[str, Any] | None:
    """fio's --output file can contain multiple concatenated JSON blobs when
    --status-interval is set. Scan for complete objects by depth and return
    the final one, which is fio's cumulative summary for the run.
    """
    last: dict[str, Any] | None = None
    depth = 0
    buf: list[str] = []
    for ch in text:
        if ch == "{":
            depth += 1
        if depth > 0:
            buf.append(ch)
        if ch == "}":
            depth -= 1
            if depth == 0 and buf:
                raw = "".join(buf).strip()
                buf.clear()
                try:
                    last = json.loads(raw)
                except json.JSONDecodeError:
                    continue
    return last


def _terminate(proc: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        return


def _snapshot_to_sample(phase_name: str, snapshot: dict[str, Any]) -> dict[str, Any] | None:
    jobs = snapshot.get("jobs") or []
    if not jobs:
        return None
    job = jobs[0]
    read = job.get("read", {}) or {}
    write = job.get("write", {}) or {}
    return {
        "phase_name": phase_name,
        "elapsed_s": job.get("elapsed", 0),
        "eta_s": job.get("eta", 0),
        "read_iops": _safe_float(read.get("iops")),
        "read_bw_bytes": _safe_int(read.get("bw_bytes")),
        "read_clat_mean_ns": _nested_float(read, "clat_ns", "mean"),
        "write_iops": _safe_float(write.get("iops")),
        "write_bw_bytes": _safe_int(write.get("bw_bytes")),
        "write_clat_mean_ns": _nested_float(write, "clat_ns", "mean"),
    }


def _summarise(fio_result: dict[str, Any]) -> dict[str, Any]:
    jobs = fio_result.get("jobs") or []
    if not jobs:
        return {}
    job = jobs[0]
    read = job.get("read", {}) or {}
    write = job.get("write", {}) or {}

    def _pctl(section: dict[str, Any], key: str) -> float | None:
        pct = (section.get("clat_ns") or {}).get("percentile") or {}
        return _safe_float(pct.get(PERCENTILE_MAP[key]))

    return {
        "read_iops": _safe_float(read.get("iops")),
        "read_bw_bytes": _safe_int(read.get("bw_bytes")),
        "read_clat_mean_ns": _nested_float(read, "clat_ns", "mean"),
        "read_clat_p50_ns": _pctl(read, "p50"),
        "read_clat_p99_ns": _pctl(read, "p99"),
        "read_clat_p999_ns": _pctl(read, "p999"),
        "read_clat_p9999_ns": _pctl(read, "p9999"),
        "write_iops": _safe_float(write.get("iops")),
        "write_bw_bytes": _safe_int(write.get("bw_bytes")),
        "write_clat_mean_ns": _nested_float(write, "clat_ns", "mean"),
        "write_clat_p50_ns": _pctl(write, "p50"),
        "write_clat_p99_ns": _pctl(write, "p99"),
        "write_clat_p999_ns": _pctl(write, "p999"),
        "write_clat_p9999_ns": _pctl(write, "p9999"),
    }


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _nested_float(section: dict[str, Any], *keys: str) -> float | None:
    current: Any = section
    for k in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(k)
    return _safe_float(current)
