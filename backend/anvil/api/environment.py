from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from anvil.api import require_bearer
from anvil.auth import require_admin
from anvil.config import get_settings
from anvil.orchestrator import audit as audit_write
from anvil.runner import get_runner_client

router = APIRouter(prefix="/environment", tags=["environment"], dependencies=[Depends(require_bearer)])


class TuneRequest(BaseModel):
    keys: list[str] | None = None


class TuneRevertRequest(BaseModel):
    results: list[dict[str, Any]]


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
async def tune_apply(body: TuneRequest) -> dict[str, Any]:
    """Apply the full tuning set (or a named subset). Records an audit-log row.

    Admin-only because this writes to host sysfs and changes benchmark
    reproducibility guarantees. The response contains every path touched
    with before / after / ok so the caller can later POST the same
    results back to /tune/revert for a clean undo.
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
    await audit_write(
        actor="tune_apply",
        action="env_tune_apply",
        target=None,
        details={"keys": body.keys, "receipt": receipt},
    )
    return receipt


@router.post("/tune/revert", dependencies=[Depends(require_admin)])
async def tune_revert(body: TuneRevertRequest) -> dict[str, Any]:
    """Revert a prior apply. Pass the `results` list from the apply response."""
    settings = get_settings()
    client = get_runner_client(settings.runner_socket)
    try:
        receipt = await client.tune_revert(body.results)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Runner unreachable: {exc}",
        ) from exc
    await audit_write(
        actor="tune_revert",
        action="env_tune_revert",
        target=None,
        details={"receipt": receipt},
    )
    return receipt
