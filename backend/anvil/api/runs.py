from __future__ import annotations

import re

import ulid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from anvil.api import require_bearer
from anvil.auth import require_operator
from anvil.db import get_session
from anvil.models import Device, Run, RunMetric, RunPhase, RunStatus
from anvil.orchestrator import audit, get_queue
from anvil.profiles import get_profile, list_profiles
from anvil.profiles.snia import RoundObservation, evaluate_steady_state
from anvil.reports import render_run_html, render_run_json_bundle
from anvil.schemas import MetricPoint, ProfileOut, RunCreate, RunOut, RunSummary
from anvil.shares import generate_slug

router = APIRouter(prefix="/runs", tags=["runs"], dependencies=[Depends(require_bearer)])


@router.get("/profiles", response_model=list[ProfileOut])
async def profiles() -> list[ProfileOut]:
    return [ProfileOut(**p.as_dict()) for p in list_profiles()]


@router.get("", response_model=list[RunSummary])
async def list_runs(
    session: AsyncSession = Depends(get_session), limit: int = 50
) -> list[RunSummary]:
    stmt = (
        select(Run)
        .options(selectinload(Run.device))
        .order_by(Run.queued_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    out: list[RunSummary] = []
    for run in result.scalars():
        device = run.device
        out.append(
            RunSummary(
                id=run.id,
                device_id=run.device_id,
                device_model=device.model if device else "?",
                device_serial=device.serial if device else "?",
                profile_name=run.profile_name,
                status=run.status,
                queued_at=run.queued_at,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )
        )
    return out


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED,
              dependencies=[Depends(require_operator)])
async def create_run(
    payload: RunCreate, session: AsyncSession = Depends(get_session)
) -> Run:
    device = await session.get(Device, payload.device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    profile = get_profile(payload.profile_name)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown profile")

    if not device.is_testable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Device is not testable: {device.exclusion_reason or 'unknown reason'}",
        )

    if profile.destructive:
        supplied = (payload.confirm_serial_last6 or "").strip().lower()
        expected = device.serial.strip().lower()[-6:]
        if not expected or supplied != expected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Destructive run requires last-6 of device serial for confirmation",
            )

    device_path = device.current_device_path
    if not device_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device has no current path; rescan before running",
        )

    run = Run(
        id=str(ulid.ULID()),
        device_id=device.id,
        profile_name=profile.name,
        profile_snapshot=profile.as_dict(),
        status=RunStatus.QUEUED.value,
        device_path_at_run=device_path,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run, ["phases"])

    await audit(
        actor="api",
        action="run_queued",
        target=run.id,
        details={"device_id": device.id, "profile": profile.name},
    )

    await get_queue().submit(run.id)
    return run


@router.post("/{run_id}/abort", dependencies=[Depends(require_operator)])
async def abort_run(
    run_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status in (RunStatus.COMPLETE.value, RunStatus.FAILED.value, RunStatus.ABORTED.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run already in terminal status: {run.status}",
        )
    result = await get_queue().abort(run_id)
    await audit(actor="api", action="run_aborted", target=run_id, details={"result": result})
    return {"run_id": run_id, "result": result}


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)) -> Run:
    stmt = select(Run).options(selectinload(Run.phases)).where(Run.id == run_id)
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.get("/{run_id}/timeseries", response_model=list[MetricPoint])
async def get_timeseries(
    run_id: str,
    metric: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[MetricPoint]:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    stmt = select(RunMetric).where(RunMetric.run_id == run_id)
    if metric:
        stmt = stmt.where(RunMetric.metric_name == metric)
    stmt = stmt.order_by(RunMetric.ts.asc())
    result = await session.execute(stmt)
    return [
        MetricPoint(ts=m.ts, metric_name=m.metric_name, value=m.value)
        for m in result.scalars()
    ]


@router.get("/{run_id}/phases")
async def get_run_phases(
    run_id: str, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """Compact phase summary with timing info, used by the UI to annotate charts."""
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    result = await session.execute(
        select(RunPhase)
        .where(RunPhase.run_id == run_id)
        .order_by(RunPhase.phase_order.asc())
    )
    out: list[dict] = []
    for p in result.scalars():
        out.append(
            {
                "id": p.id,
                "phase_order": p.phase_order,
                "phase_name": p.phase_name,
                "pattern": p.pattern,
                "block_size": p.block_size,
                "iodepth": p.iodepth,
                "numjobs": p.numjobs,
                "rwmix_write_pct": p.rwmix_write_pct,
                "runtime_s": p.runtime_s,
                "started_at": p.started_at,
                "finished_at": p.finished_at,
                "read_iops": p.read_iops,
                "read_bw_bytes": p.read_bw_bytes,
                "read_clat_mean_ns": p.read_clat_mean_ns,
                "read_clat_p99_ns": p.read_clat_p99_ns,
                "read_clat_p9999_ns": p.read_clat_p9999_ns,
                "write_iops": p.write_iops,
                "write_bw_bytes": p.write_bw_bytes,
                "write_clat_mean_ns": p.write_clat_mean_ns,
                "write_clat_p99_ns": p.write_clat_p99_ns,
                "write_clat_p9999_ns": p.write_clat_p9999_ns,
            }
        )
    return out


def _extract_clat_bins(fio_result: dict | None) -> dict[str, list[tuple[int, int]]]:
    """Return {"read": [(bin_ns, count), ...], "write": [...]} from a fio json+ result.

    fio's json+ output nests latency bins at jobs[].read.clat_ns.bins as a
    {bin_ns_str: count} dict. We aggregate across every job in the result to
    handle numjobs > 1 runs where each job reports its own histogram.
    """
    out: dict[str, list[tuple[int, int]]] = {"read": [], "write": []}
    if not fio_result:
        return out
    jobs = fio_result.get("jobs") or []
    agg: dict[str, dict[int, int]] = {"read": {}, "write": {}}
    for job in jobs:
        for direction in ("read", "write"):
            section = job.get(direction)
            if not isinstance(section, dict):
                continue
            clat = section.get("clat_ns")
            if not isinstance(clat, dict):
                continue
            bins = clat.get("bins")
            if not isinstance(bins, dict):
                continue
            for k, v in bins.items():
                try:
                    bin_ns = int(k)
                    count = int(v)
                except (TypeError, ValueError):
                    continue
                if count <= 0:
                    continue
                agg[direction][bin_ns] = agg[direction].get(bin_ns, 0) + count
    for d in ("read", "write"):
        out[d] = sorted(agg[d].items(), key=lambda kv: kv[0])
    return out


@router.get("/{run_id}/phases/{phase_id}/histogram")
async def get_phase_histogram(
    run_id: str,
    phase_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Latency histogram + exceedance CDF for one phase, derived from fio json+ bins."""
    phase = await session.get(RunPhase, phase_id)
    if phase is None or phase.run_id != run_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phase not found")
    bins = _extract_clat_bins(phase.fio_result)

    directions: dict[str, dict] = {}
    for direction, arr in bins.items():
        if not arr:
            continue
        total = sum(c for _, c in arr)
        if total <= 0:
            continue
        histogram = [{"bin_ns": b, "count": c} for b, c in arr]
        running = 0
        cdf: list[dict] = []
        for b, c in arr:
            running += c
            cdf.append(
                {
                    "bin_ns": b,
                    "cdf": running / total,
                    "exceedance": max(0.0, 1.0 - running / total),
                }
            )
        directions[direction] = {
            "total_ios": total,
            "histogram": histogram,
            "cdf": cdf,
        }

    return {
        "run_id": run_id,
        "phase_id": phase_id,
        "phase_name": phase.phase_name,
        "directions": directions,
    }


_SNIA_PHASE_RE = re.compile(r"^snia_r(\d+)_bs([^_]+)_w(\d+)$")


@router.get("/{run_id}/snia-analysis")
async def get_snia_analysis(
    run_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Fit SNIA-PTS steady-state math over a run's round-structured phases.

    Groups completed phases by round index parsed from the phase name
    (snia_r<N>_bs<BS>_w<WPCT>), extracts the 4 KiB 100% write IOPS per
    round as the SNIA canonical convergence metric, and returns both the
    per-round raw data (every cell in the matrix) and the
    `evaluate_steady_state` output. Works for the static snia_quick_pts
    profile; later adaptive SNIA profiles can emit the same phase-name
    shape and light this up automatically.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    result = await session.execute(
        select(RunPhase)
        .where(RunPhase.run_id == run_id)
        .order_by(RunPhase.phase_order.asc())
    )
    by_round: dict[int, list[dict]] = {}
    for p in result.scalars():
        m = _SNIA_PHASE_RE.match(p.phase_name)
        if not m:
            continue
        rnd = int(m.group(1))
        bs_label = m.group(2)
        wpct = int(m.group(3))
        cell = {
            "phase_id": p.id,
            "phase_name": p.phase_name,
            "block_size_label": bs_label,
            "rwmix_write_pct": wpct,
            "iodepth": p.iodepth,
            "numjobs": p.numjobs,
            "runtime_s": p.runtime_s,
            "read_iops": p.read_iops,
            "write_iops": p.write_iops,
            "read_bw_bytes": p.read_bw_bytes,
            "write_bw_bytes": p.write_bw_bytes,
            "read_clat_p99_ns": p.read_clat_p99_ns,
            "write_clat_p99_ns": p.write_clat_p99_ns,
        }
        by_round.setdefault(rnd, []).append(cell)

    rounds_summary: list[dict] = []
    observations: list[RoundObservation] = []
    for rnd in sorted(by_round.keys()):
        cells = by_round[rnd]
        canonical = next(
            (c for c in cells if c["block_size_label"] == "4k" and c["rwmix_write_pct"] == 100),
            None,
        )
        metric_value = canonical["write_iops"] if canonical else None
        rounds_summary.append(
            {
                "round_idx": rnd,
                "cells": cells,
                "canonical_4k_100w_iops": metric_value,
            }
        )
        if metric_value is not None:
            observations.append(RoundObservation(round_idx=rnd, metric=float(metric_value)))

    ss = evaluate_steady_state(observations)
    return {
        "run_id": run_id,
        "profile": run.profile_name,
        "rounds": rounds_summary,
        "steady_state": {
            "steady": ss.steady,
            "reason": ss.reason,
            "rounds_observed": ss.rounds_observed,
            "window": ss.window,
            "window_mean": ss.window_mean,
            "window_range": ss.window_range,
            "range_limit": ss.range_limit,
            "range_ok": ss.range_ok,
            "slope_per_round": ss.slope_per_round,
            "slope_across_window": ss.slope_across_window,
            "slope_limit": ss.slope_limit,
            "slope_ok": ss.slope_ok,
        },
    }


async def _assemble_export(
    run_id: str, session: AsyncSession
) -> tuple[dict, list[dict], list[dict], dict | None]:
    stmt = select(Run).options(selectinload(Run.phases)).where(Run.id == run_id)
    run = (await session.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    run_dict = {
        "id": run.id,
        "device_id": run.device_id,
        "profile_name": run.profile_name,
        "status": run.status,
        "queued_at": run.queued_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "error_message": run.error_message,
        "device_path_at_run": run.device_path_at_run,
        "host_system": run.host_system,
        "smart_before": run.smart_before,
        "smart_after": run.smart_after,
    }
    phases = [
        {
            "id": p.id,
            "phase_order": p.phase_order,
            "phase_name": p.phase_name,
            "pattern": p.pattern,
            "block_size": p.block_size,
            "iodepth": p.iodepth,
            "numjobs": p.numjobs,
            "runtime_s": p.runtime_s,
            "started_at": p.started_at,
            "finished_at": p.finished_at,
            "read_iops": p.read_iops,
            "read_bw_bytes": p.read_bw_bytes,
            "read_clat_mean_ns": p.read_clat_mean_ns,
            "read_clat_p99_ns": p.read_clat_p99_ns,
            "read_clat_p9999_ns": p.read_clat_p9999_ns,
            "write_iops": p.write_iops,
            "write_bw_bytes": p.write_bw_bytes,
            "write_clat_mean_ns": p.write_clat_mean_ns,
            "write_clat_p99_ns": p.write_clat_p99_ns,
        }
        for p in sorted(run.phases, key=lambda x: x.phase_order)
    ]
    ts_rows = (
        await session.execute(
            select(RunMetric).where(RunMetric.run_id == run_id).order_by(RunMetric.ts.asc())
        )
    ).scalars()
    timeseries = [
        {"ts": m.ts.isoformat(), "metric_name": m.metric_name, "value": m.value}
        for m in ts_rows
    ]
    device = None
    dev = await session.get(Device, run.device_id)
    if dev is not None:
        device = {
            "id": dev.id,
            "model": dev.model,
            "serial": dev.serial,
            "firmware": dev.firmware,
            "vendor": dev.vendor,
            "protocol": dev.protocol,
            "capacity_bytes": dev.capacity_bytes,
            "pcie": (dev.metadata_json or {}).get("pcie"),
        }
    return run_dict, phases, timeseries, device


@router.get("/{run_id}/export.html", response_class=HTMLResponse)
async def export_run_html(
    run_id: str, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    """Self-contained, printable HTML report for one run. Zero JS."""
    run_dict, phases, timeseries, device = await _assemble_export(run_id, session)
    html = render_run_html(
        run=run_dict, phases=phases, timeseries=timeseries, device=device,
    )
    return HTMLResponse(
        content=html,
        headers={
            "Content-Disposition": f'inline; filename="anvil-run-{run_id}.html"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                "font-src data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
            ),
        },
    )


@router.get("/{run_id}/export.json")
async def export_run_json(
    run_id: str, session: AsyncSession = Depends(get_session)
) -> Response:
    """Lossless JSON bundle of every persisted artefact for one run."""
    run_dict, phases, timeseries, device = await _assemble_export(run_id, session)
    payload = render_run_json_bundle(
        run=run_dict, phases=phases, timeseries=timeseries, device=device,
    )
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="anvil-run-{run_id}.json"',
        },
    )


@router.get("/{run_id}/share")
async def get_run_share(
    run_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return {"run_id": run.id, "share_slug": run.share_slug}


@router.post("/{run_id}/share", dependencies=[Depends(require_operator)])
async def create_run_share(
    run_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    run.share_slug = generate_slug()
    await session.commit()
    return {"run_id": run.id, "share_slug": run.share_slug}


@router.delete("/{run_id}/share", dependencies=[Depends(require_operator)])
async def revoke_run_share(
    run_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    run.share_slug = None
    await session.commit()
    return {"run_id": run.id, "share_slug": None}
