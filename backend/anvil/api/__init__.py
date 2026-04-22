from __future__ import annotations

from fastapi import Depends

from anvil.auth import (
    Principal,
    require_admin,
    require_operator,
    require_viewer,
    resolve_principal,
)


async def require_bearer(principal: Principal = Depends(resolve_principal)) -> Principal:
    """Back-compat shim: resolves to any authenticated principal (token or user).

    Any `Depends(require_bearer)` site now gets a Principal; legacy code paths
    that didn't care about the object and only needed 401/403 enforcement
    still work because an auth failure aborts before reaching the handler.
    New code should use the role-scoped dependencies from anvil.auth.
    """
    return principal


__all__ = [
    "Principal",
    "require_admin",
    "require_bearer",
    "require_operator",
    "require_viewer",
    "resolve_principal",
]
