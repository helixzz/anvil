from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from anvil.db import get_session
from anvil.models import Device, Run, RunMetric, SavedComparison
from anvil.reports import render_run_html

router = APIRouter(prefix="/r", tags=["public"])


async def _load_run_for_export(
    run_id: str, session: AsyncSession
) -> tuple[dict, list[dict], list[dict], dict | None]:
    run = (
        await session.execute(
            select(Run).options(selectinload(Run.phases)).where(Run.id == run_id)
        )
    ).scalar_one_or_none()
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
        "host_system": run.host_system,
        "smart_before": run.smart_before,
        "smart_after": run.smart_after,
    }
    phases = [
        {
            "phase_order": p.phase_order,
            "phase_name": p.phase_name,
            "pattern": p.pattern,
            "block_size": p.block_size,
            "iodepth": p.iodepth,
            "numjobs": p.numjobs,
            "runtime_s": p.runtime_s,
            "read_iops": p.read_iops,
            "read_bw_bytes": p.read_bw_bytes,
            "read_clat_mean_ns": p.read_clat_mean_ns,
            "read_clat_p99_ns": p.read_clat_p99_ns,
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
            "model": dev.model,
            "serial": dev.serial,
            "firmware": dev.firmware,
            "vendor": dev.vendor,
            "protocol": dev.protocol,
            "capacity_bytes": dev.capacity_bytes,
        }
    return run_dict, phases, timeseries, device


@router.get("/runs/{slug}", response_class=HTMLResponse)
async def public_run_report(
    slug: str, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    run = (
        await session.execute(select(Run).where(Run.share_slug == slug))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
    run_dict, phases, timeseries, device = await _load_run_for_export(run.id, session)
    html = render_run_html(
        run=run_dict,
        phases=phases,
        timeseries=timeseries,
        device=device,
        redact=True,
    )
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Robots-Tag": "noindex",
        },
    )


@router.get("/compare/{slug}", response_class=HTMLResponse)
async def public_comparison_report(
    slug: str, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    comp = (
        await session.execute(
            select(SavedComparison).where(SavedComparison.share_slug == slug)
        )
    ).scalar_one_or_none()
    if comp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
    run_ids = list(comp.run_ids or [])
    sections: list[str] = []
    for rid in run_ids:
        try:
            run_dict, phases, timeseries, device = await _load_run_for_export(rid, session)
        except HTTPException:
            continue
        section = render_run_html(
            run=run_dict,
            phases=phases,
            timeseries=timeseries,
            device=device,
            redact=True,
        )
        sections.append(
            f'<section style="margin:48px 0;padding-top:24px;border-top:2px solid #233256">'
            f'{section}</section>'
        )
    body = "\n".join(sections) or "<p>No runs in this comparison.</p>"
    html = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8" /><title>Anvil Comparison — {comp.name}</title>
<style>body{{background:#0b1220;color:#e2e8f0;margin:0;padding:32px;font-family:-apple-system,sans-serif}}
h1{{font-size:24px;margin:0 0 8px}}</style></head><body>
<h1>Comparison: {comp.name}</h1>
<p style="color:#94a3b8">{comp.description or ''}</p>
{body}
</body></html>"""
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Robots-Tag": "noindex",
        },
    )
