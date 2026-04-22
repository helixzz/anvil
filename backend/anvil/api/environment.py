from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from anvil.api import require_bearer
from anvil.config import get_settings
from anvil.runner import get_runner_client

router = APIRouter(prefix="/environment", tags=["environment"], dependencies=[Depends(require_bearer)])


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
