"""Auth for Anvil.

Two accepted credentials:

1. The legacy single-bearer-token set via ANVIL_BEARER_TOKEN. When
   this token is presented the request is treated as coming from the
   built-in "operator-token" principal with Administrator role; this
   keeps existing automation (CI integration tests, curl scripts)
   working without changing them.
2. A short-lived JWT (HS256) signed with the same ANVIL_BEARER_TOKEN
   secret, created by POST /api/auth/login with a username + password
   that match a User row. Claims: sub=user_id, username, role, exp.

Every API handler that needs authorization depends on require_role(...)
which accepts the minimum role needed. Order is viewer < operator <
admin.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anvil.config import Settings, get_settings
from anvil.db import get_session
from anvil.models import User, UserRole

BCRYPT_MAX_PASSWORD_BYTES = 72
BCRYPT_ROUNDS = 12

ROLE_ORDER = {
    UserRole.VIEWER.value: 1,
    UserRole.OPERATOR.value: 2,
    UserRole.ADMIN.value: 3,
}

JWT_ALG = "HS256"
JWT_TTL_SECONDS = 60 * 60 * 12  # 12 h
JWT_ISSUER = "anvil"


class Principal:
    """Authenticated caller. Either a User row or the bearer-token
    fallback synthetic 'operator-token' principal (admin role)."""

    def __init__(
        self,
        user_id: str | None,
        username: str,
        role: str,
        is_token: bool = False,
    ):
        self.user_id = user_id
        self.username = username
        self.role = role
        self.is_token = is_token

    @classmethod
    def from_token(cls) -> Principal:
        return cls(
            user_id=None,
            username="operator-token",
            role=UserRole.ADMIN.value,
            is_token=True,
        )

    @classmethod
    def from_user(cls, u: User) -> Principal:
        return cls(user_id=u.id, username=u.username, role=u.role, is_token=False)

    def role_rank(self) -> int:
        return ROLE_ORDER.get(self.role, 0)

    def has_role(self, min_role: str) -> bool:
        need = ROLE_ORDER.get(min_role, 0)
        return self.role_rank() >= need


def _safe_password_bytes(plain: str) -> bytes:
    """bcrypt rejects inputs > 72 bytes. Truncate rather than raise so a very
    long password (or a bearer-token-derived bootstrap password with multi-
    byte UTF-8 chars) still produces a deterministic hash."""
    return plain.encode("utf-8")[:BCRYPT_MAX_PASSWORD_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(
        _safe_password_bytes(plain),
        bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_safe_password_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_jwt(user: User, *, secret: str, ttl_seconds: int = JWT_TTL_SECONDS) -> str:
    now = datetime.now(UTC)
    payload = {
        "iss": JWT_ISSUER,
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALG)


def decode_jwt(token: str, *, secret: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALG],
            issuer=JWT_ISSUER,
        )
    except jwt.InvalidTokenError:
        return None


async def resolve_principal(
    authorization: str | None = Header(default=None),
    token: str | None = None,  # accepted as ?token=... for embed links and WS
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    """Parse Authorization: Bearer <token> OR ?token=... query parameter.

    The query-parameter form is for browser-initiated GETs (export.html,
    export.json, WebSocket upgrade) where the Authorization header can't
    be attached. For state-changing requests prefer the header.
    """
    raw: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1].strip()
    elif token:
        raw = token.strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if raw == settings.bearer_token:
        return Principal.from_token()

    claims = decode_jwt(raw, secret=settings.bearer_token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid credential"
        )
    uid = claims.get("sub")
    if not uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token claims")
    user = await session.get(User, uid)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User inactive or unknown"
        )
    if user.role != claims.get("role"):
        # Role was revoked since this JWT was issued — force re-auth.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Role changed; sign in again"
        )
    return Principal.from_user(user)


def require_role(min_role: str):
    """Dependency factory: asserts the principal has at least `min_role`."""

    async def _dep(principal: Principal = Depends(resolve_principal)) -> Principal:
        if not principal.has_role(min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{min_role}' required",
            )
        return principal

    return _dep


require_viewer = require_role(UserRole.VIEWER.value)
require_operator = require_role(UserRole.OPERATOR.value)
require_admin = require_role(UserRole.ADMIN.value)


async def authenticate_password(
    session: AsyncSession, username: str, password: str
) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return user
