from __future__ import annotations

import re
import statistics
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from anvil.api import require_bearer
from anvil.api.models import _brand_for, _model_slug
from anvil.db import get_session
from anvil.models import Device, Run, RunStatus

router = APIRouter(
    prefix="/profile-compare",
    tags=["profile-compare"],
    dependencies=[Depends(require_bearer)],
)

KIB = 1024
BS_MAP = {
    "512b": 512, "1k": KIB, "2k": 2*KIB, "4k": 4*KIB,
    "8k": 8*KIB, "16k": 16*KIB, "32k": 32*KIB, "64k": 64*KIB,
    "128k": 128*KIB, "1m": 1024*KIB,
}
BS_ORDER = ["512b", "1k", "2k", "4k", "8k", "16k", "32k", "64k", "128k", "1m"]


def _parse_phase_dimensions(name: str) -> dict[str, Any] | None:
    """Extract structured dimensions from a phase name.

    Returns dict with keys: group, pattern, bs_label, bs_bytes, qd, threads.
    Returns None if the name doesn't encode parseable dimensions.
    """
    dims: dict[str, Any] = {"raw_name": name}

    # ezfio style: ezfio_g1_seq_read_4k_q256
    m = re.match(r"ezfio_g(\d+)_(.+?)_(\d+k|512b|1m)_q(\d+)(?:t(\d+))?$", name)
    if m:
        dims["group"] = f"g{m.group(1)}"
        dims["pattern"] = m.group(2)
        dims["bs_label"] = m.group(3)
        dims["bs_bytes"] = BS_MAP.get(m.group(3), 0)
        dims["qd"] = int(m.group(4))
        dims["threads"] = int(m.group(5)) if m.group(5) else 1
        return dims

    # ezfio thread sweep: ezfio_g4_rnd_4k_read_q1t16
    m = re.match(r"ezfio_g(\d+)_(.+?)_q(\d+)t(\d+)$", name)
    if m:
        dims["group"] = f"g{m.group(1)}"
        dims["pattern"] = m.group(2)
        dims["qd"] = int(m.group(3))
        dims["threads"] = int(m.group(4))
        bs_m = re.search(r"(\d+k|512b|1m)", m.group(2))
        dims["bs_label"] = bs_m.group(1) if bs_m else "4k"
        dims["bs_bytes"] = BS_MAP.get(dims["bs_label"], 4096)
        return dims

    # sr_deep style: sr_deep_4k_read_qd16t4
    m = re.match(r"sr_deep_(\d+k|128k|64k|16k|4k)_(read|write)_qd(\d+)t(\d+)$", name)
    if m:
        dims["group"] = f"sr_{m.group(1)}_{m.group(2)}"
        dims["pattern"] = m.group(2)
        dims["bs_label"] = m.group(1)
        dims["bs_bytes"] = BS_MAP.get(m.group(1), 0)
        dims["qd"] = int(m.group(3))
        dims["threads"] = int(m.group(4))
        return dims

    # sr_four_corners: sr_4k_rand_read_128t
    m = re.match(r"sr_(\d+k)_(rand_read|rand_write|seq_read|seq_write)_(\d+)t$", name)
    if m:
        dims["group"] = "four_corners"
        dims["pattern"] = m.group(2)
        dims["bs_label"] = m.group(1)
        dims["bs_bytes"] = BS_MAP.get(m.group(1), 0)
        dims["qd"] = 1
        dims["threads"] = int(m.group(3))
        return dims

    # snia style: snia_r1_bs4k_w0
    m = re.match(r"snia_r(\d+)_bs(\d+k|1m)_w(\d+)$", name)
    if m:
        dims["group"] = f"snia_r{m.group(1)}"
        dims["bs_label"] = m.group(2)
        dims["bs_bytes"] = BS_MAP.get(m.group(2), 0)
        dims["pattern"] = f"w{m.group(3)}"
        dims["qd"] = 32
        dims["threads"] = 2
        return dims

    # generic: rnd_4k_q32t1_read
    m = re.match(r"(.+?)_(\d+k|512b|1m)_q(\d+)t?(\d+)?_(read|write|mix\w+)$", name)
    if m:
        dims["group"] = "generic"
        dims["pattern"] = m.group(5)
        dims["bs_label"] = m.group(2)
        dims["bs_bytes"] = BS_MAP.get(m.group(2), 0)
        dims["qd"] = int(m.group(3))
        dims["threads"] = int(m.group(4)) if m.group(4) else 1
        return dims

    return None


METRIC_KEYS = (
    "read_iops",
    "write_iops",
    "read_bw_bytes",
    "write_bw_bytes",
    "read_clat_mean_ns",
    "read_clat_p99_ns",
    "write_clat_mean_ns",
    "write_clat_p99_ns",
)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _phase_medians(runs: list[Run]) -> dict[str, dict[str, Any]]:
    """Per phase name: dimensions plus the median of each metric across `runs`."""
    dims_by_name: dict[str, dict[str, Any]] = {}
    order_by_name: dict[str, int] = {}
    values: dict[str, dict[str, list[float]]] = {}
    for run in runs:
        for phase in run.phases:
            dims = _parse_phase_dimensions(phase.phase_name)
            if dims is None:
                continue
            dims_by_name.setdefault(phase.phase_name, dims)
            order_by_name.setdefault(phase.phase_name, phase.phase_order)
            bucket = values.setdefault(phase.phase_name, {k: [] for k in METRIC_KEYS})
            for k in METRIC_KEYS:
                v = getattr(phase, k)
                if v is not None:
                    bucket[k].append(float(v))
    out: dict[str, dict[str, Any]] = {}
    for name in sorted(dims_by_name, key=lambda n: order_by_name[n]):
        out[name] = {
            **dims_by_name[name],
            **{k: _median(values[name][k]) for k in METRIC_KEYS},
            "_samples": values[name],
        }
    return out


def _with_spread(point: dict[str, Any], samples: dict[str, list[float]]) -> dict[str, Any]:
    """Attach `spread[metric] = {min, max, n}` and drop internal fields."""
    clean = {k: v for k, v in point.items() if k != "_samples"}
    clean["spread"] = {
        k: {"min": min(vs), "max": max(vs), "n": len(vs)}
        for k, vs in samples.items()
        if vs
    }
    return clean


async def _complete_runs(
    session: AsyncSession, profile_name: str, device_ids: list[str]
) -> dict[str, list[Run]]:
    rows = (await session.execute(
        select(Run)
        .options(selectinload(Run.phases))
        .where(Run.device_id.in_(device_ids))
        .where(Run.profile_name == profile_name)
        .where(Run.status == RunStatus.COMPLETE.value)
    )).scalars().all()
    by_device: dict[str, list[Run]] = {}
    for run in rows:
        by_device.setdefault(run.device_id, []).append(run)
    return by_device


def _device_series(dev: Device, runs: list[Run]) -> dict[str, Any]:
    """One drive: median over its complete runs; spread = run-to-run range."""
    medians = _phase_medians(runs)
    latest = max(runs, key=lambda r: r.finished_at or r.queued_at)
    return {
        "key": dev.id,
        "kind": "device",
        "device_id": dev.id,
        "model": dev.model,
        "serial": dev.serial,
        "brand": _brand_for(dev),
        "firmwares": [dev.firmware] if dev.firmware else [],
        "unit_count": 1,
        "run_count": len(runs),
        "run_id": latest.id,
        "points": [_with_spread(pt, pt["_samples"]) for pt in medians.values()],
    }


def _model_series(
    slug: str, devices: list[Device], runs_by_device: dict[str, list[Run]]
) -> dict[str, Any] | None:
    """One product model: median across drives of each drive's own median.

    Collapsing repeats per drive first keeps a drive with more runs from
    dominating the model figure; spread is the drive-to-drive range, which
    is what reveals a weak unit or a firmware difference.
    """
    tested = [d for d in devices if runs_by_device.get(d.id)]
    if not tested:
        return None
    per_device = {d.id: _phase_medians(runs_by_device[d.id]) for d in tested}
    names: list[str] = []
    for medians in per_device.values():
        for name in medians:
            if name not in names:
                names.append(name)

    points: list[dict[str, Any]] = []
    for name in names:
        dims = next(m[name] for m in per_device.values() if name in m)
        unit_values: dict[str, list[float]] = {k: [] for k in METRIC_KEYS}
        for medians in per_device.values():
            pt = medians.get(name)
            if pt is None:
                continue
            for k in METRIC_KEYS:
                if pt[k] is not None:
                    unit_values[k].append(pt[k])
        point = {
            **{k: v for k, v in dims.items() if k not in METRIC_KEYS and k != "_samples"},
            **{k: _median(unit_values[k]) for k in METRIC_KEYS},
        }
        points.append(_with_spread(point, unit_values))

    first = tested[0]
    return {
        "key": slug,
        "kind": "model",
        "model_slug": slug,
        "model": first.model,
        "serial": "",
        "brand": _brand_for(first),
        "firmwares": sorted({d.firmware for d in tested if d.firmware}),
        "unit_count": len(tested),
        "run_count": sum(len(runs_by_device[d.id]) for d in tested),
        "units": [
            {
                "device_id": d.id,
                "serial": d.serial,
                "firmware": d.firmware,
                "run_count": len(runs_by_device[d.id]),
            }
            for d in sorted(tested, key=lambda d: d.serial)
        ],
        "points": points,
    }


def _split_csv(value: str | None) -> list[str]:
    return list(dict.fromkeys(v.strip() for v in (value or "").split(",") if v.strip()))


@router.get("/candidates")
async def compare_candidates(
    profile_name: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Models and drives that have at least one complete run of `profile_name`."""
    counts = dict((await session.execute(
        select(Run.device_id, func.count(Run.id))
        .where(Run.profile_name == profile_name)
        .where(Run.status == RunStatus.COMPLETE.value)
        .group_by(Run.device_id)
    )).all())
    if not counts:
        return {"profile_name": profile_name, "models": [], "devices": []}
    devices = (await session.execute(
        select(Device).where(Device.id.in_(list(counts)))
    )).scalars().all()

    models: dict[str, dict[str, Any]] = {}
    device_rows: list[dict[str, Any]] = []
    for d in devices:
        slug = _model_slug(d.vendor, d.model)
        entry = models.setdefault(slug, {
            "model_slug": slug,
            "brand": _brand_for(d),
            "model": d.model,
            "unit_count": 0,
            "run_count": 0,
            "firmwares": set(),
        })
        entry["unit_count"] += 1
        entry["run_count"] += counts[d.id]
        if d.firmware:
            entry["firmwares"].add(d.firmware)
        device_rows.append({
            "device_id": d.id,
            "model_slug": slug,
            "brand": _brand_for(d),
            "model": d.model,
            "serial": d.serial,
            "firmware": d.firmware,
            "run_count": counts[d.id],
        })
    model_rows = [
        {**m, "firmwares": sorted(m["firmwares"])}
        for m in sorted(models.values(), key=lambda m: (m["brand"], m["model"]))
    ]
    device_rows.sort(key=lambda r: (r["brand"], r["model"], r["serial"]))
    return {"profile_name": profile_name, "models": model_rows, "devices": device_rows}


@router.get("")
async def profile_compare(
    profile_name: str,
    device_ids: str | None = None,
    model_slugs: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Comparison data for one profile, one series per product model or per drive.

    - `model_slugs`: one series per model, aggregated over every drive of
      that model with complete runs (median of per-drive medians).
    - `device_ids`: one series per drive, the median over its complete runs.

    Each point carries the median metrics plus `spread` (min/max/n): the
    drive-to-drive range for models, the run-to-run range for drives.
    """
    slugs = _split_csv(model_slugs)
    dids = _split_csv(device_ids)
    if bool(slugs) == bool(dids):
        raise HTTPException(status_code=400, detail="pass exactly one of model_slugs or device_ids")

    series: list[dict[str, Any]] = []
    if slugs:
        wanted = set(slugs)
        devices_by_slug: dict[str, list[Device]] = {}
        for d in (await session.execute(select(Device))).scalars():
            slug = _model_slug(d.vendor, d.model)
            if slug in wanted:
                devices_by_slug.setdefault(slug, []).append(d)
        all_ids = [d.id for ds in devices_by_slug.values() for d in ds]
        runs_by_device = await _complete_runs(session, profile_name, all_ids) if all_ids else {}
        for slug in slugs:
            entry = _model_series(slug, devices_by_slug.get(slug, []), runs_by_device)
            if entry is not None:
                series.append(entry)
    else:
        devices = {
            d.id: d
            for d in (await session.execute(select(Device).where(Device.id.in_(dids)))).scalars()
        }
        runs_by_device = await _complete_runs(session, profile_name, list(devices))
        for did in dids:
            if did in devices and runs_by_device.get(did):
                series.append(_device_series(devices[did], runs_by_device[did]))

    groups = sorted({p.get("group", "other") for s in series for p in s["points"]})
    return {
        "profile_name": profile_name,
        "group_by": "model" if slugs else "device",
        "series": series,
        "groups": groups,
    }
