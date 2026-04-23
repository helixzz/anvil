from __future__ import annotations

from typing import Any

import ulid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from anvil.api import require_bearer
from anvil.auth import Principal, require_admin, resolve_principal
from anvil.config import get_settings
from anvil.db import get_session
from anvil.models import TuneReceipt
from anvil.orchestrator import audit as audit_write
from anvil.runner import get_runner_client

router = APIRouter(prefix="/environment", tags=["environment"], dependencies=[Depends(require_bearer)])


class TuneRequest(BaseModel):
    keys: list[str] | None = None


class TuneRevertRequest(BaseModel):
    receipt_id: str


@router.get("")
async def get_environment() -> dict[str, Any]:
    """Run every host-environment check via the privileged runner and return the report.

    The runner's probe walks host /proc, /sys, and /proc/1/root paths (via the
    nsenter prefix and pid=host mount) to see the real CPU governor settings,
    PCIe ASPM policy, NVMe APST state, block-layer scheduler, load average,
    and tool versions - not the container's restricted view.
    """
    settings = get_settings()
    client = get_runner_client(settings.runner_socket)
    try:
        result = await client.environment()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Runner unreachable: {exc}",
        ) from exc
    checks = result.get("checks") or []
    summary = {
        "total": len(checks),
        "pass": sum(1 for c in checks if c.get("status") == "pass"),
        "warn": sum(1 for c in checks if c.get("status") == "warn"),
        "fail": sum(1 for c in checks if c.get("status") == "fail"),
        "info": sum(1 for c in checks if c.get("status") == "info"),
    }
    return {"summary": summary, "checks": checks}


@router.get("/tune/preview", dependencies=[Depends(require_admin)])
async def tune_preview(keys: str | None = None) -> dict[str, Any]:
    """Dry-run: return every path that would change and the value it would become.

    `keys` is an optional comma-separated list of TUNABLE key names
    (cpu_governor, pcie_aspm_policy, nvme_scheduler, nvme_nr_requests,
    nvme_read_ahead_kb). If omitted, every tunable is previewed.
    """
    settings = get_settings()
    client = get_runner_client(settings.runner_socket)
    key_list = [s.strip() for s in keys.split(",")] if keys else None
    try:
        return await client.tune_preview(key_list)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Runner unreachable: {exc}",
        ) from exc


@router.post("/tune/apply", dependencies=[Depends(require_admin)])
async def tune_apply(
    body: TuneRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Apply the full tuning set (or a named subset). Persists an
    opaque receipt server-side; pass the receipt_id to /tune/revert for
    a safe undo.

    The server never accepts a caller-supplied revert payload. Revert
    reads the stored receipt by ID, so a malicious client cannot
    redirect the privileged sysfs write to arbitrary paths.
    """
    settings = get_settings()
    client = get_runner_client(settings.runner_socket)
    try:
        receipt = await client.tune_apply(body.keys)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Runner unreachable: {exc}",
        ) from exc
    receipt_id = str(ulid.ULID())
    session.add(TuneReceipt(
        id=receipt_id,
        results=receipt.get("results") or [],
        reverted=False,
        created_by=principal.user_id,
    ))
    await audit_write(
        actor=principal.username,
        action="env_tune_apply",
        target=receipt_id,
        details={"keys": body.keys, "entries": len(receipt.get("results") or [])},
    )
    await session.commit()
    return {"receipt_id": receipt_id, **receipt}


@router.post("/tune/revert", dependencies=[Depends(require_admin)])
async def tune_revert(
    body: TuneRevertRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Revert a prior apply by receipt_id.

    Loads the apply-time results from the database, not from the
    request body, so a malicious client cannot substitute an arbitrary
    (path, value) pair to trigger an unauthorized privileged write.
    The runner additionally enforces a sysfs-glob allowlist as
    defense-in-depth.
    """
    stored = await session.get(TuneReceipt, body.receipt_id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="receipt not found"
        )
    if stored.reverted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="receipt already reverted"
        )
    settings = get_settings()
    client = get_runner_client(settings.runner_socket)
    try:
        receipt = await client.tune_revert(list(stored.results or []))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Runner unreachable: {exc}",
        ) from exc
    stored.reverted = True
    await audit_write(
        actor=principal.username,
        action="env_tune_revert",
        target=body.receipt_id,
        details={"entries": len(stored.results or [])},
    )
    await session.commit()
    return {"receipt_id": body.receipt_id, **receipt}
