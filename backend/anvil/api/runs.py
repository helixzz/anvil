from __future__ import annotations

import ulid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from anvil.api import require_bearer
from anvil.db import get_session
from anvil.models import Device, Run, RunMetric, RunPhase, RunStatus
from anvil.orchestrator import audit, get_queue
from anvil.profiles import get_profile, list_profiles
from anvil.schemas import MetricPoint, ProfileOut, RunCreate, RunOut, RunSummary

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


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED)
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
