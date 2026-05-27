from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from anvil.api import require_bearer
from anvil.db import get_session
from anvil.models import Device, Run, RunPhase, RunStatus

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


def _best_metric(phase: RunPhase) -> dict[str, Any]:
    return {
        "read_iops": phase.read_iops,
        "write_iops": phase.write_iops,
        "read_bw_bytes": phase.read_bw_bytes,
        "write_bw_bytes": phase.write_bw_bytes,
        "read_clat_mean_ns": phase.read_clat_mean_ns,
        "read_clat_p99_ns": phase.read_clat_p99_ns,
        "write_clat_mean_ns": phase.write_clat_mean_ns,
        "write_clat_p99_ns": phase.write_clat_p99_ns,
    }


@router.get("")
async def profile_compare(
    profile_name: str,
    device_ids: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return structured comparison data for one profile across multiple devices.

    Groups phases by their encoded dimensions (block size, QD, threads)
    and returns chart-ready series data where each series is one device.
    """
    did_list = [d.strip() for d in device_ids.split(",") if d.strip()]
    if not did_list:
        raise HTTPException(status_code=400, detail="device_ids required")

    devices_map: dict[str, Device] = {}
    for did in did_list:
        dev = await session.get(Device, did)
        if dev:
            devices_map[did] = dev

    series: list[dict[str, Any]] = []

    for did, dev in devices_map.items():
        runs = (await session.execute(
            select(Run)
            .options(selectinload(Run.phases))
            .where(Run.device_id == did)
            .where(Run.profile_name == profile_name)
            .where(Run.status == RunStatus.COMPLETE.value)
            .order_by(Run.finished_at.desc())
            .limit(1)
        )).scalars().all()

        if not runs:
            continue

        run = runs[0]
        points: list[dict[str, Any]] = []
        for phase in sorted(run.phases, key=lambda p: p.phase_order):
            dims = _parse_phase_dimensions(phase.phase_name)
            if dims is None:
                continue
            point = {**dims, **_best_metric(phase)}
            points.append(point)

        series.append({
            "device_id": did,
            "model": dev.model,
            "serial": dev.serial,
            "brand": dev.vendor or dev.brand or "",
            "run_id": run.id,
            "points": points,
        })

    groups: dict[str, list[str]] = {}
    for s in series:
        for p in s["points"]:
            g = p.get("group", "other")
            if g not in groups:
                groups[g] = []

    return {
        "profile_name": profile_name,
        "series": series,
        "groups": sorted(groups.keys()),
    }
