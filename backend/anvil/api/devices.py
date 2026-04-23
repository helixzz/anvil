from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import ulid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from anvil.api import require_bearer
from anvil.auth import require_operator
from anvil.db import get_session
from anvil.discovery import discover
from anvil.models import Device, DeviceSnapshot, Run
from anvil.schemas import DeviceOut

router = APIRouter(prefix="/devices", tags=["devices"], dependencies=[Depends(require_bearer)])


_VENDOR_KEYWORDS = (
    ("SAMSUNG", "Samsung"),
    ("INTEL", "Intel"),
    ("SOLIDIGM", "Solidigm"),
    ("MICRON", "Micron"),
    ("CRUCIAL", "Crucial"),
    ("KIOXIA", "Kioxia"),
    ("TOSHIBA", "Toshiba"),
    ("WESTERN DIGITAL", "WDC"),
    ("SANDISK", "SanDisk"),
    ("HGST", "HGST"),
    ("SEAGATE", "Seagate"),
    ("KINGSTON", "Kingston"),
    ("SK HYNIX", "SK Hynix"),
    ("HYNIX", "SK Hynix"),
    ("DAPUSTOR", "DapuStor"),
    ("HUAWEI", "Huawei"),
    ("ADATA", "ADATA"),
    ("CORSAIR", "Corsair"),
    ("LEXAR", "Lexar"),
    ("PHISON", "Phison"),
    ("MAXIO", "Maxio"),
    ("REALTEK", "Realtek"),
)


def _vendor_from_product(product_name: str) -> str | None:
    if not product_name:
        return None
    upper = product_name.upper()
    for needle, canonical in _VENDOR_KEYWORDS:
        if needle in upper:
            return canonical
    return None


@router.get("", response_model=list[DeviceOut])
async def list_devices(session: AsyncSession = Depends(get_session)) -> list[Device]:
    result = await session.execute(select(Device).order_by(Device.last_seen.desc()))
    return list(result.scalars())


@router.post("/rescan", response_model=list[DeviceOut], dependencies=[Depends(require_operator)])
async def rescan(session: AsyncSession = Depends(get_session)) -> list[Device]:
    found = await discover()
    now = datetime.now(UTC)

    existing_by_fp: dict[str, Device] = {
        d.fingerprint: d for d in (await session.execute(select(Device))).scalars()
    }

    result: list[Device] = []
    for d in found:
        device = existing_by_fp.get(d.fingerprint)
        if device is None:
            device = Device(
                id=str(ulid.ULID()),
                fingerprint=d.fingerprint,
                wwid=d.wwid,
                model=d.model,
                serial=d.serial,
                firmware=d.firmware,
                vendor=_vendor_from_product(d.product_name),
                protocol=d.protocol,
                capacity_bytes=d.size_bytes,
                sector_size_logical=d.sector_size_logical,
                sector_size_physical=d.sector_size_physical,
                is_testable=d.is_testable,
                exclusion_reason=d.exclusion_reason,
                current_device_path=d.path,
                first_seen=now,
                last_seen=now,
                metadata_json={
                    "rotational": d.rotational,
                    "partitions": d.partitions,
                    "mount_points": d.mount_points,
                    "product_name": d.product_name,
                    "pcie": d.pcie,
                },
            )
            session.add(device)
        else:
            device.model = d.model or device.model
            device.serial = d.serial or device.serial
            device.firmware = d.firmware or device.firmware
            device.vendor = _vendor_from_product(d.product_name) or device.vendor
            device.protocol = d.protocol
            device.capacity_bytes = d.size_bytes or device.capacity_bytes
            device.sector_size_logical = d.sector_size_logical or device.sector_size_logical
            device.sector_size_physical = d.sector_size_physical or device.sector_size_physical
            device.is_testable = d.is_testable
            device.exclusion_reason = d.exclusion_reason
            device.current_device_path = d.path
            device.last_seen = now
            device.metadata_json = {
                **(device.metadata_json or {}),
                "rotational": d.rotational,
                "partitions": d.partitions,
                "mount_points": d.mount_points,
                "product_name": d.product_name,
                "pcie": d.pcie,
            }

        snapshot = DeviceSnapshot(
            id=str(ulid.ULID()),
            device_id=device.id,
            captured_at=now,
            raw_lsblk=d.raw_lsblk,
            raw_nvme_list=d.raw_nvme,
            pcie=d.pcie,
            parsed={
                "path": d.path,
                "is_testable": d.is_testable,
                "exclusion_reason": d.exclusion_reason,
                "firmware": d.firmware,
                "size_bytes": d.size_bytes,
            },
        )
        session.add(snapshot)
        result.append(device)

    await session.commit()
    refreshed = await session.execute(select(Device).order_by(Device.last_seen.desc()))
    return list(refreshed.scalars())


@router.get("/{device_id}/history")
async def get_device_history(
    device_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Return all complete runs for this device with headline metrics, in time order.

    Powers the device detail page's regression timeline: the UI renders a small
    line chart per metric so you can spot a drive degrading run-over-run or
    correlate a firmware change with a performance shift.
    """
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    runs_result = await session.execute(
        select(Run)
        .where(Run.device_id == device_id)
        .options(selectinload(Run.phases))
        .order_by(Run.finished_at.asc().nullslast(), Run.queued_at.asc())
    )
    entries: list[dict[str, Any]] = []
    for r in runs_result.scalars():
        best_read_iops = max(
            (p.read_iops for p in r.phases if p.read_iops is not None),
            default=None,
        )
        best_write_iops = max(
            (p.write_iops for p in r.phases if p.write_iops is not None),
            default=None,
        )
        best_read_bw = max(
            (p.read_bw_bytes for p in r.phases if p.read_bw_bytes is not None),
            default=None,
        )
        best_write_bw = max(
            (p.write_bw_bytes for p in r.phases if p.write_bw_bytes is not None),
            default=None,
        )
        entries.append(
            {
                "id": r.id,
                "profile_name": r.profile_name,
                "status": r.status,
                "queued_at": r.queued_at,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "best_read_iops": best_read_iops,
                "best_write_iops": best_write_iops,
                "best_read_bw_bytes": best_read_bw,
                "best_write_bw_bytes": best_write_bw,
                "phase_count": len(r.phases),
            }
        )

    firmware_changes: list[dict[str, Any]] = []
    last_firmware: str | None = None
    snap_result = await session.execute(
        select(DeviceSnapshot)
        .where(DeviceSnapshot.device_id == device_id)
        .order_by(DeviceSnapshot.captured_at.asc())
    )
    for snap in snap_result.scalars():
        parsed = snap.parsed or {}
        fw = parsed.get("firmware")
        if fw and fw != last_firmware:
            firmware_changes.append({"captured_at": snap.captured_at, "firmware": fw})
            last_firmware = fw

    return {
        "device_id": device_id,
        "model": device.model,
        "serial": device.serial,
        "firmware": device.firmware,
        "pcie": (device.metadata_json or {}).get("pcie"),
        "runs": entries,
        "firmware_changes": firmware_changes,
    }


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: str, session: AsyncSession = Depends(get_session)) -> Device:
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


@router.get("/{device_id}/snapshots")
async def get_snapshots(
    device_id: str, session: AsyncSession = Depends(get_session), limit: int = 20
) -> list[dict[str, Any]]:
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    result = await session.execute(
        select(DeviceSnapshot)
        .where(DeviceSnapshot.device_id == device_id)
        .order_by(DeviceSnapshot.captured_at.desc())
        .limit(limit)
    )
    out = []
    for snap in result.scalars():
        out.append(
            {
                "id": snap.id,
                "captured_at": snap.captured_at,
                "parsed": snap.parsed,
                "has_nvme": snap.raw_nvme_list is not None,
                "has_smart": snap.raw_smart is not None,
            }
        )
    return out


class PhysicalLocation(BaseModel):
    chassis: str | None = None
    bay: str | None = None
    tray: str | None = None
    port: str | None = None
    notes: str | None = None


@router.patch("/{device_id}/location", dependencies=[Depends(require_operator)])
async def set_device_location(
    device_id: str,
    body: PhysicalLocation,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    payload = {k: v for k, v in body.model_dump().items() if v is not None and v != ""}
    device.physical_location = payload or None
    await session.commit()
    return {"device_id": device_id, "physical_location": device.physical_location}
