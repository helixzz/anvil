from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from anvil.api import require_bearer
from anvil.db import get_session
from anvil.models import Device, Run, RunMetric, RunPhase

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(require_bearer)])


def _model_slug(vendor: str | None, model: str) -> str:
    parts: list[str] = []
    if vendor:
        parts.append(vendor)
    parts.append(model)
    return " ".join(parts).strip().replace("/", "_").replace(" ", "-")


def _brand_for(device: Device) -> str:
    if device.vendor:
        return device.vendor
    return _infer_brand(device.model)


def _infer_brand(model: str) -> str:
    m = model.upper()
    for brand in (
        "SAMSUNG", "INTEL", "SOLIDIGM", "MICRON", "WESTERN DIGITAL", "WDC", "WD",
        "SEAGATE", "HITACHI", "HGST", "TOSHIBA", "KIOXIA", "CRUCIAL",
        "SANDISK", "KINGSTON", "CORSAIR", "SK HYNIX", "HYNIX", "DAPUSTOR",
        "HUAWEI", "LEXAR", "ADATA",
    ):
        if brand in m:
            return brand.title() if brand != "WDC" else "WDC"
    return model.split()[0] if model else "Unknown"


@router.get("")
async def list_models(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    """Aggregate devices into model entries with run counts and headline metrics."""
    result = await session.execute(
        select(Device).options(selectinload(Device.runs))
    )
    models: dict[str, dict[str, Any]] = {}
    for d in result.scalars():
        brand = _brand_for(d)
        key = _model_slug(brand, d.model)
        entry = models.setdefault(
            key,
            {
                "slug": key,
                "brand": brand,
                "model": d.model,
                "protocol": d.protocol,
                "form_factor": d.form_factor,
                "capacity_bytes_samples": [],
                "device_count": 0,
                "run_count": 0,
                "firmwares": set(),
                "last_run_at": None,
            },
        )
        entry["device_count"] += 1
        if d.capacity_bytes:
            entry["capacity_bytes_samples"].append(d.capacity_bytes)
        if d.firmware:
            entry["firmwares"].add(d.firmware)
        complete_runs = [
            r for r in d.runs if r.status == "complete" and r.finished_at is not None
        ]
        entry["run_count"] += len(complete_runs)
        for r in complete_runs:
            if entry["last_run_at"] is None or (
                r.finished_at and r.finished_at > entry["last_run_at"]
            ):
                entry["last_run_at"] = r.finished_at

    output: list[dict[str, Any]] = []
    for entry in models.values():
        caps = entry.pop("capacity_bytes_samples")
        entry["capacity_bytes_typical"] = max(caps) if caps else None
        entry["firmwares"] = sorted(entry["firmwares"])
        output.append(entry)
    output.sort(key=lambda e: (e["brand"], e["model"]))
    return output


@router.get("/{slug}")
async def model_detail(
    slug: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    all_devices = (await session.execute(select(Device))).scalars().all()
    matching = [d for d in all_devices if _model_slug(_brand_for(d), d.model) == slug]
    if not matching:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    device_ids = [d.id for d in matching]
    runs_result = await session.execute(
        select(Run)
        .where(Run.device_id.in_(device_ids))
        .order_by(Run.finished_at.desc().nullslast(), Run.queued_at.desc())
    )
    runs = list(runs_result.scalars())

    profiles_used: dict[str, int] = {}
    for r in runs:
        profiles_used[r.profile_name] = profiles_used.get(r.profile_name, 0) + 1

    headline_metrics = await _compute_headline(session, device_ids)
    stability = await _compute_stability(session, [r.id for r in runs if r.status == "complete"])

    return {
        "slug": slug,
        "brand": _brand_for(matching[0]),
        "model": matching[0].model,
        "protocol": matching[0].protocol,
        "form_factor": matching[0].form_factor,
        "capacity_bytes_typical": max((d.capacity_bytes or 0 for d in matching), default=None),
        "firmwares": sorted({d.firmware for d in matching if d.firmware}),
        "devices": [
            {
                "id": d.id,
                "serial": d.serial,
                "firmware": d.firmware,
                "first_seen": d.first_seen,
                "last_seen": d.last_seen,
                "is_testable": d.is_testable,
            }
            for d in matching
        ],
        "runs": [
            {
                "id": r.id,
                "device_id": r.device_id,
                "profile_name": r.profile_name,
                "status": r.status,
                "queued_at": r.queued_at,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            }
            for r in runs
        ],
        "profiles_used": profiles_used,
        "headline_metrics": headline_metrics,
        "stability": stability,
    }


async def _compute_headline(
    session: AsyncSession, device_ids: list[str]
) -> dict[str, Any]:
    """Best, median and worst IOPS / BW per representative phase across all runs of this model."""
    stmt = (
        select(
            RunPhase.phase_name,
            RunPhase.pattern,
            RunPhase.block_size,
            RunPhase.iodepth,
            func.max(
                case((RunPhase.read_iops.isnot(None), RunPhase.read_iops), else_=RunPhase.write_iops)
            ).label("best_iops"),
            func.max(
                case(
                    (RunPhase.read_bw_bytes.isnot(None), RunPhase.read_bw_bytes),
                    else_=RunPhase.write_bw_bytes,
                )
            ).label("best_bw_bytes"),
            func.count(RunPhase.id).label("sample_count"),
        )
        .join(Run, Run.id == RunPhase.run_id)
        .where(Run.device_id.in_(device_ids))
        .where(Run.status == "complete")
        .group_by(RunPhase.phase_name, RunPhase.pattern, RunPhase.block_size, RunPhase.iodepth)
        .order_by(RunPhase.phase_name)
    )
    rows = (await session.execute(stmt)).all()
    return {
        "per_phase": [
            {
                "phase_name": row.phase_name,
                "pattern": row.pattern,
                "block_size": row.block_size,
                "iodepth": row.iodepth,
                "best_iops": row.best_iops,
                "best_bw_bytes": row.best_bw_bytes,
                "sample_count": row.sample_count,
            }
            for row in rows
        ]
    }


async def _compute_stability(
    session: AsyncSession, run_ids: list[str]
) -> dict[str, Any]:
    """Rough performance / thermal stability score over all complete runs of the model.

    For IOPS: coefficient of variation (stddev / mean) of all per-second samples
    during the model's runs. Lower CV is better. We express it as a 0-100 score
    where 100 = CV <= 2% (near-constant), 0 = CV >= 50%.

    For temperature: (max - min) across all samples. A small range is good; we
    score 100 when range <= 5 C, 0 when range >= 30 C.
    """
    if not run_ids:
        return {"iops_score": None, "temperature_score": None, "iops_cv": None, "temp_range_c": None}

    iops_stmt = (
        select(
            func.avg(RunMetric.value).label("mean"),
            func.stddev_samp(RunMetric.value).label("sd"),
            func.count(RunMetric.value).label("n"),
        )
        .where(RunMetric.run_id.in_(run_ids))
        .where(RunMetric.metric_name.in_(["read_iops", "write_iops"]))
    )
    iops_row = (await session.execute(iops_stmt)).one()
    iops_cv: float | None = None
    iops_score: float | None = None
    if iops_row.n and iops_row.mean and iops_row.mean > 0 and iops_row.sd is not None:
        iops_cv = float(iops_row.sd) / float(iops_row.mean)
        iops_score = _score_01_to_100(iops_cv, good=0.02, bad=0.50, invert=True)

    temp_stmt = (
        select(func.min(RunMetric.value), func.max(RunMetric.value), func.count(RunMetric.value))
        .where(RunMetric.run_id.in_(run_ids))
        .where(RunMetric.metric_name == "temperature_c")
    )
    tmin, tmax, tn = (await session.execute(temp_stmt)).one()
    temp_range: float | None = None
    temp_score: float | None = None
    if tn and tmin is not None and tmax is not None:
        temp_range = float(tmax) - float(tmin)
        temp_score = _score_01_to_100(temp_range, good=5.0, bad=30.0, invert=True)

    return {
        "iops_score": iops_score,
        "iops_cv": iops_cv,
        "iops_sample_count": iops_row.n,
        "temperature_score": temp_score,
        "temp_range_c": temp_range,
        "temp_sample_count": tn,
    }


def _score_01_to_100(value: float, good: float, bad: float, invert: bool = False) -> float:
    if invert:
        if value <= good:
            return 100.0
        if value >= bad:
            return 0.0
        return 100.0 * (bad - value) / (bad - good)
    if value >= good:
        return 100.0
    if value <= bad:
        return 0.0
    return 100.0 * (value - bad) / (good - bad)


@router.get("/{slug}/compare")
async def compare_phase(
    slug: str,
    phase_name: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """All instances of a particular phase for a model (cross-run comparison for same test)."""
    all_devices = (await session.execute(select(Device))).scalars().all()
    matching_ids = [
        d.id for d in all_devices
        if _model_slug(_brand_for(d), d.model) == slug
    ]
    if not matching_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    stmt = (
        select(RunPhase, Run)
        .join(Run, Run.id == RunPhase.run_id)
        .where(Run.device_id.in_(matching_ids))
        .where(Run.status == "complete")
        .where(RunPhase.phase_name == phase_name)
        .order_by(Run.finished_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    return {
        "phase_name": phase_name,
        "samples": [
            {
                "run_id": run.id,
                "device_id": run.device_id,
                "finished_at": run.finished_at,
                "read_iops": phase.read_iops,
                "read_bw_bytes": phase.read_bw_bytes,
                "read_clat_mean_ns": phase.read_clat_mean_ns,
                "read_clat_p99_ns": phase.read_clat_p99_ns,
                "read_clat_p9999_ns": phase.read_clat_p9999_ns,
                "write_iops": phase.write_iops,
                "write_bw_bytes": phase.write_bw_bytes,
                "write_clat_mean_ns": phase.write_clat_mean_ns,
                "write_clat_p99_ns": phase.write_clat_p99_ns,
            }
            for phase, run in rows
        ],
    }


@router.get("/compare/common-phases")
async def common_phases_across_models(
    slugs: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return phase_names that every selected model has at least one complete run of.

    Used by the Compare workbench so the phase selector only offers phases we
    can actually render for the full selection.
    """
    slug_list = [s for s in slugs.split(",") if s.strip()]
    if not slug_list:
        return {"slugs": [], "phase_names": []}
    all_devices = (await session.execute(select(Device))).scalars().all()
    model_to_device_ids: dict[str, list[str]] = {}
    for d in all_devices:
        key = _model_slug(_brand_for(d), d.model)
        if key in slug_list:
            model_to_device_ids.setdefault(key, []).append(d.id)

    if set(model_to_device_ids.keys()) != set(slug_list):
        missing = sorted(set(slug_list) - set(model_to_device_ids.keys()))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown model slug(s): {missing}",
        )

    phase_sets: list[set[str]] = []
    for device_ids in model_to_device_ids.values():
        stmt = (
            select(RunPhase.phase_name)
            .join(Run, Run.id == RunPhase.run_id)
            .where(Run.device_id.in_(device_ids))
            .where(Run.status == "complete")
            .distinct()
        )
        names = {row[0] for row in (await session.execute(stmt)).all()}
        phase_sets.append(names)

    common = sorted(set.intersection(*phase_sets)) if phase_sets else []
    return {"slugs": slug_list, "phase_names": common}


@router.get("/compare")
async def compare_across_models(
    slugs: str,
    phase_name: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Aggregate one phase's samples across multiple models for side-by-side comparison.

    For each selected model we compute mean / median / best read-IOPS,
    read-BW, mean latency, p99 latency across every complete run that ran
    the named phase, plus the raw sample list so the UI can show both a
    roll-up bar chart and a scatter of individual runs.
    """
    slug_list = [s for s in slugs.split(",") if s.strip()]
    if not slug_list:
        return {"phase_name": phase_name, "models": []}

    all_devices = (await session.execute(select(Device))).scalars().all()
    slug_to_device_ids: dict[str, list[str]] = {}
    for d in all_devices:
        key = _model_slug(_brand_for(d), d.model)
        if key in slug_list:
            slug_to_device_ids.setdefault(key, []).append(d.id)

    models_out: list[dict[str, Any]] = []
    for slug in slug_list:
        device_ids = slug_to_device_ids.get(slug) or []
        if not device_ids:
            models_out.append(
                {"slug": slug, "brand": None, "model": None, "samples": [], "summary": {}}
            )
            continue
        rep = next((d for d in all_devices if d.id in device_ids), None)
        stmt = (
            select(RunPhase, Run)
            .join(Run, Run.id == RunPhase.run_id)
            .where(Run.device_id.in_(device_ids))
            .where(Run.status == "complete")
            .where(RunPhase.phase_name == phase_name)
            .order_by(Run.finished_at.asc())
        )
        rows = (await session.execute(stmt)).all()
        samples: list[dict[str, Any]] = []
        for phase, run in rows:
            samples.append(
                {
                    "run_id": run.id,
                    "device_id": run.device_id,
                    "finished_at": run.finished_at,
                    "read_iops": phase.read_iops,
                    "read_bw_bytes": phase.read_bw_bytes,
                    "read_clat_mean_ns": phase.read_clat_mean_ns,
                    "read_clat_p99_ns": phase.read_clat_p99_ns,
                    "write_iops": phase.write_iops,
                    "write_bw_bytes": phase.write_bw_bytes,
                    "write_clat_mean_ns": phase.write_clat_mean_ns,
                    "write_clat_p99_ns": phase.write_clat_p99_ns,
                }
            )
        summary = _summarise_samples(samples)
        models_out.append(
            {
                "slug": slug,
                "brand": _brand_for(rep) if rep else None,
                "model": rep.model if rep else None,
                "device_count": len(device_ids),
                "samples": samples,
                "summary": summary,
            }
        )

    return {"phase_name": phase_name, "models": models_out}


def _summarise_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    from statistics import mean, median

    def collect(key: str) -> list[float]:
        return [float(s[key]) for s in samples if s.get(key) not in (None, 0)]

    out: dict[str, Any] = {"sample_count": len(samples)}
    for key in (
        "read_iops", "read_bw_bytes",
        "write_iops", "write_bw_bytes",
        "read_clat_mean_ns", "read_clat_p99_ns",
        "write_clat_mean_ns", "write_clat_p99_ns",
    ):
        vals = collect(key)
        if not vals:
            out[key] = None
            continue
        out[key] = {
            "mean": mean(vals),
            "median": median(vals),
            "best": max(vals) if "iops" in key or "bw" in key else min(vals),
            "count": len(vals),
        }
    return out
