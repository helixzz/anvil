from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from anvil.config import Settings, get_settings


def require_bearer(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.bearer_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bearer token"
        )
