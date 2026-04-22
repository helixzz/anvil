from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from anvil.api import require_bearer
from anvil.api.models import _brand_for, _model_slug
from anvil.db import get_session
from anvil.models import Device, Run, RunPhase

router = APIRouter(
    prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(require_bearer)]
)


@router.get("/fleet-stats")
async def fleet_stats(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Hero numbers for the dashboard: device count, run count, TiB written, distinct models."""
    device_count = (await session.execute(select(func.count(Device.id)))).scalar_one()
    testable_count = (
        await session.execute(
            select(func.count(Device.id)).where(Device.is_testable.is_(True))
        )
    ).scalar_one()
    total_runs = (await session.execute(select(func.count(Run.id)))).scalar_one()
    complete_runs = (
        await session.execute(
            select(func.count(Run.id)).where(Run.status == "complete")
        )
    ).scalar_one()
    failed_runs = (
        await session.execute(
            select(func.count(Run.id)).where(Run.status == "failed")
        )
    ).scalar_one()
    aborted_runs = (
        await session.execute(
            select(func.count(Run.id)).where(Run.status == "aborted")
        )
    ).scalar_one()

    bytes_written_total = (
        await session.execute(
            select(func.coalesce(func.sum(RunPhase.write_bw_bytes * RunPhase.runtime_s), 0))
            .join(Run, Run.id == RunPhase.run_id)
            .where(Run.status == "complete")
        )
    ).scalar_one()

    devices_result = await session.execute(select(Device))
    distinct_models: set[str] = set()
    distinct_brands: set[str] = set()
    for d in devices_result.scalars():
        distinct_models.add(_model_slug(_brand_for(d), d.model))
        distinct_brands.add(_brand_for(d))

    return {
        "device_count": device_count,
        "testable_device_count": testable_count,
        "distinct_models": len(distinct_models),
        "distinct_brands": len(distinct_brands),
        "total_runs": total_runs,
        "complete_runs": complete_runs,
        "failed_runs": failed_runs,
        "aborted_runs": aborted_runs,
        "approx_bytes_written": int(bytes_written_total or 0),
    }


@router.get("/leaderboards")
async def leaderboards(
    session: AsyncSession = Depends(get_session), limit: int = 5
) -> dict[str, Any]:
    """Top-N rankings across a few canonical metrics.

    For each category we return the top `limit` RunPhase rows with device
    + model info joined in. Categories chosen to show different corners of
    the storage-performance space: QD1 latency sensitivity, QD32 random
    throughput, sequential large-block throughput, and p99 latency QoS.
    """
    categories: dict[str, dict[str, Any]] = {
        "rnd_4k_q1_read_iops": {
            "title": "4K QD1 random read IOPS",
            "order": RunPhase.read_iops.desc(),
            "metric": "read_iops",
            "filter": lambda q: q.where(
                RunPhase.pattern == "randread",
                RunPhase.block_size == 4096,
                RunPhase.iodepth == 1,
            ),
        },
        "rnd_4k_q32_read_iops": {
            "title": "4K QD32 random read IOPS",
            "order": RunPhase.read_iops.desc(),
            "metric": "read_iops",
            "filter": lambda q: q.where(
                RunPhase.pattern == "randread",
                RunPhase.block_size == 4096,
                RunPhase.iodepth == 32,
            ),
        },
        "seq_1m_q8_read_bw": {
            "title": "1 MiB QD8 sequential read BW",
            "order": RunPhase.read_bw_bytes.desc(),
            "metric": "read_bw_bytes",
            "filter": lambda q: q.where(
                RunPhase.pattern == "read",
                RunPhase.block_size == 1 << 20,
                RunPhase.iodepth == 8,
            ),
        },
        "rnd_4k_q32_read_p99": {
            "title": "4K QD32 random read p99 latency (lowest is best)",
            "order": RunPhase.read_clat_p99_ns.asc(),
            "metric": "read_clat_p99_ns",
            "filter": lambda q: q.where(
                RunPhase.pattern == "randread",
                RunPhase.block_size == 4096,
                RunPhase.iodepth == 32,
                RunPhase.read_clat_p99_ns.isnot(None),
            ),
        },
    }

    out: dict[str, Any] = {}
    for key, cfg in categories.items():
        base = (
            select(RunPhase, Run, Device)
            .join(Run, Run.id == RunPhase.run_id)
            .join(Device, Device.id == Run.device_id)
            .where(Run.status == "complete")
        )
        base = cfg["filter"](base).order_by(cfg["order"]).limit(limit)
        rows = (await session.execute(base)).all()
        entries: list[dict[str, Any]] = []
        for phase, run, device in rows:
            entries.append(
                {
                    "run_id": run.id,
                    "device_id": device.id,
                    "brand": _brand_for(device),
                    "model": device.model,
                    "finished_at": run.finished_at,
                    "value": getattr(phase, cfg["metric"]),
                    "read_iops": phase.read_iops,
                    "read_bw_bytes": phase.read_bw_bytes,
                    "read_clat_mean_ns": phase.read_clat_mean_ns,
                    "read_clat_p99_ns": phase.read_clat_p99_ns,
                }
            )
        out[key] = {
            "title": cfg["title"],
            "metric": cfg["metric"],
            "entries": entries,
        }
    return out


@router.get("/pcie-degraded")
async def pcie_degraded_devices(
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List every testable device whose PCIe link is running below its capability."""
    result = await session.execute(select(Device))
    out: list[dict[str, Any]] = []
    for d in result.scalars():
        pcie = (d.metadata_json or {}).get("pcie")
        if not pcie or not pcie.get("degraded"):
            continue
        out.append(
            {
                "device_id": d.id,
                "brand": _brand_for(d),
                "model": d.model,
                "serial": d.serial,
                "capability": pcie.get("capability"),
                "status": pcie.get("status"),
                "speed_degraded": pcie.get("speed_degraded"),
                "width_degraded": pcie.get("width_degraded"),
            }
        )
    return out


@router.get("/activity")
async def activity_timeline(
    session: AsyncSession = Depends(get_session), days: int = 30
) -> dict[str, Any]:
    """Per-day run counts and cumulative bytes-written over the last N days."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(Run, RunPhase)
        .outerjoin(RunPhase, RunPhase.run_id == Run.id)
        .where(Run.queued_at >= cutoff)
    )
    rows = (await session.execute(stmt)).all()

    per_day: dict[str, dict[str, int]] = {}
    for day_offset in range(days):
        day = (datetime.now(UTC) - timedelta(days=days - day_offset - 1)).strftime("%Y-%m-%d")
        per_day[day] = {"total": 0, "complete": 0, "failed": 0, "aborted": 0}

    seen_runs: set[str] = set()
    for run, _ in rows:
        if run.id in seen_runs:
            continue
        seen_runs.add(run.id)
        day = run.queued_at.strftime("%Y-%m-%d")
        if day not in per_day:
            continue
        per_day[day]["total"] += 1
        if run.status in ("complete", "failed", "aborted"):
            per_day[day][run.status] += 1

    return {
        "days": days,
        "series": [
            {
                "day": day,
                **counts,
            }
            for day, counts in sorted(per_day.items())
        ],
    }


@router.get("/alarms")
async def recent_alarms(
    session: AsyncSession = Depends(get_session), hours: int = 24
) -> list[dict[str, Any]]:
    """Any run that failed or was aborted in the last N hours."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(Run)
        .options(selectinload(Run.device))
        .where(Run.status.in_(["failed", "aborted"]))
        .where(Run.finished_at >= cutoff)
        .order_by(Run.finished_at.desc())
        .limit(20)
    )
    rows = (await session.execute(stmt)).scalars()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "run_id": r.id,
                "device_id": r.device_id,
                "model": r.device.model if r.device else None,
                "profile": r.profile_name,
                "status": r.status,
                "finished_at": r.finished_at,
                "error_message": r.error_message,
            }
        )
    return out
