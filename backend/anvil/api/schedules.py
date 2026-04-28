from __future__ import annotations

import ulid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anvil.auth import Principal, require_admin, resolve_principal
from anvil.db import get_session
from anvil.models import Device, Schedule

router = APIRouter(
    prefix="/schedules",
    tags=["schedules"],
    dependencies=[Depends(require_admin)],
)


class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    device_id: str
    profile_name: str
    interval_hours: int = Field(gt=0)
    enabled: bool = True


class ScheduleOut(BaseModel):
    id: str
    name: str
    device_id: str
    profile_name: str
    enabled: bool
    interval_hours: int
    last_run_at: str | None
    next_run_at: str | None
    created_by: str | None
    created_at: str
    updated_at: str


def _out(row: Schedule) -> ScheduleOut:
    return ScheduleOut(
        id=row.id,
        name=row.name,
        device_id=row.device_id,
        profile_name=row.profile_name,
        enabled=row.enabled,
        interval_hours=row.interval_hours,
        last_run_at=row.last_run_at.isoformat() if row.last_run_at else None,
        next_run_at=row.next_run_at.isoformat() if row.next_run_at else None,
        created_by=row.created_by,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(session: AsyncSession = Depends(get_session)) -> list[ScheduleOut]:
    rows = (await session.execute(
        select(Schedule).order_by(Schedule.created_at.desc())
    )).scalars().all()
    return [_out(r) for r in rows]


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> ScheduleOut:
    dev = await session.get(Device, body.device_id)
    if dev is None:
        raise HTTPException(status_code=404, detail="Device not found")
    row = Schedule(
        id=str(ulid.ULID()),
        name=body.name,
        device_id=body.device_id,
        profile_name=body.profile_name,
        enabled=body.enabled,
        interval_hours=body.interval_hours,
        created_by=principal.user_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _out(row)


@router.get("/{sched_id}", response_model=ScheduleOut)
async def get_schedule(sched_id: str, session: AsyncSession = Depends(get_session)) -> ScheduleOut:
    row = await session.get(Schedule, sched_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return _out(row)


@router.put("/{sched_id}", response_model=ScheduleOut)
async def update_schedule(
    sched_id: str,
    body: ScheduleIn,
    session: AsyncSession = Depends(get_session),
) -> ScheduleOut:
    row = await session.get(Schedule, sched_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    row.name = body.name
    row.device_id = body.device_id
    row.profile_name = body.profile_name
    row.interval_hours = body.interval_hours
    row.enabled = body.enabled
    await session.commit()
    await session.refresh(row)
    return _out(row)


@router.delete("/{sched_id}")
async def delete_schedule(sched_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    row = await session.get(Schedule, sched_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    await session.delete(row)
    await session.commit()
    return {"deleted": sched_id}
