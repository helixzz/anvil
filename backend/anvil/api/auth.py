from __future__ import annotations

from datetime import datetime
from typing import Any

import ulid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anvil.auth import (
    Principal,
    authenticate_password,
    create_jwt,
    hash_password,
    require_admin,
    resolve_principal,
)
from anvil.config import Settings, get_settings
from anvil.db import get_session
from anvil.models import AuditLog, User, UserRole
from anvil.sso import (
    GroupRoleMapping,
    SsoConfig,
    SsoConfigVersionConflict,
    load_sso_config,
    load_sso_config_with_version,
    provision_sso_user,
    save_sso_config,
)

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    token: str
    user: dict[str, Any]


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str | None
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    class Config:
        from_attributes = True


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)
    display_name: str | None = None
    role: str = UserRole.VIEWER.value


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=256)


def _audit(session: AsyncSession, actor: str, action: str, target: str | None, details: dict) -> None:
    session.add(AuditLog(actor=actor, action=action, target=target, details=details))


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    user = await authenticate_password(session, body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )
    token = create_jwt(user, secret=settings.bearer_token)
    _audit(session, actor=user.username, action="login", target=user.id, details={})
    await session.commit()
    return LoginResponse(
        token=token,
        user={
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "display_name": user.display_name,
        },
    )


@router.get("/auth/me")
async def me(principal: Principal = Depends(resolve_principal)) -> dict[str, Any]:
    return {
        "user_id": principal.user_id,
        "username": principal.username,
        "role": principal.role,
        "is_token": principal.is_token,
    }


admin_router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)


@admin_router.get("/users", response_model=list[UserOut])
async def list_users(session: AsyncSession = Depends(get_session)) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at.asc()))
    return list(result.scalars())


@admin_router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    principal: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> User:
    if body.role not in {r.value for r in UserRole}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"role must be one of {[r.value for r in UserRole]}",
        )
    existing = await session.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="username already in use"
        )
    user = User(
        id=str(ulid.ULID()),
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    session.add(user)
    _audit(
        session,
        actor=principal.username,
        action="user_created",
        target=user.id,
        details={"username": body.username, "role": body.role},
    )
    await session.commit()
    await session.refresh(user)
    return user


@admin_router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    principal: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    changes: dict[str, Any] = {}
    if body.display_name is not None:
        user.display_name = body.display_name
        changes["display_name"] = body.display_name
    if body.role is not None:
        if body.role not in {r.value for r in UserRole}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="invalid role"
            )
        user.role = body.role
        changes["role"] = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
        changes["is_active"] = body.is_active
    if body.new_password is not None:
        user.password_hash = hash_password(body.new_password)
        changes["password_reset"] = True
    _audit(
        session, actor=principal.username, action="user_updated", target=user.id, details=changes
    )
    await session.commit()
    await session.refresh(user)
    return user


@admin_router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    principal: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if principal.user_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="admins cannot delete themselves",
        )
    await session.delete(user)
    _audit(
        session,
        actor=principal.username,
        action="user_deleted",
        target=user.id,
        details={"username": user.username},
    )
    await session.commit()
    return {"deleted": user.id}


class MappingEntry(BaseModel):
    group: str = Field(min_length=1, max_length=256)
    role: str = Field(min_length=1, max_length=32)


class SsoConfigRequest(BaseModel):
    enabled: bool = False
    idp_metadata_url: str = ""
    idp_entity_id: str = ""
    sp_entity_id: str = "anvil"
    sp_acs_url: str = ""
    username_attribute: str = "uid"
    display_name_attribute: str = "displayName"
    email_attribute: str = "mail"
    groups_attribute: str = "memberOf"
    default_role: str = UserRole.VIEWER.value
    mappings: list[MappingEntry] = Field(default_factory=list)
    expected_version: str | None = None


class SsoAssertionRequest(BaseModel):
    """Inputs for the admin-only SSO provisioning smoke test.

    The sibling endpoint `/auth/sso/assertion` MUST remain admin-gated
    because these attributes are caller-supplied and would otherwise be
    a straight auth bypass. A real SAML ACS would populate these fields
    only after validating the XML AuthnResponse signature, issuer,
    NotOnOrAfter window, and replay nonce.
    """

    username: str = Field(min_length=1)
    display_name: str | None = None
    groups: list[str] = Field(default_factory=list)


@router.get("/auth/sso/config")
async def get_sso_config(
    principal: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    config, version = await load_sso_config_with_version(session)
    out = config.as_dict()
    out["version"] = version
    return out


@router.put("/auth/sso/config")
async def put_sso_config(
    body: SsoConfigRequest,
    principal: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    for m in body.mappings:
        if m.role not in {r.value for r in UserRole}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid role in mapping: {m.role}",
            )
    if body.default_role not in {r.value for r in UserRole}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid default_role: {body.default_role}",
        )
    config = SsoConfig(
        enabled=body.enabled,
        idp_metadata_url=body.idp_metadata_url,
        idp_entity_id=body.idp_entity_id,
        sp_entity_id=body.sp_entity_id,
        sp_acs_url=body.sp_acs_url,
        username_attribute=body.username_attribute,
        display_name_attribute=body.display_name_attribute,
        email_attribute=body.email_attribute,
        groups_attribute=body.groups_attribute,
        default_role=body.default_role,
        mappings=[GroupRoleMapping(group=m.group, role=m.role) for m in body.mappings],
    )
    try:
        new_version = await save_sso_config(
            session, config, expected_version=body.expected_version
        )
    except SsoConfigVersionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SSO config changed by another admin; reload before editing. ({exc})",
        ) from exc
    _audit(
        session,
        actor=principal.username,
        action="sso_config_updated",
        target=None,
        details=config.as_dict(),
    )
    await session.commit()
    out = config.as_dict()
    out["version"] = new_version
    return out


@router.post("/auth/sso/assertion")
async def sso_assertion(
    body: SsoAssertionRequest,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    """Admin-only SSO provisioning smoke test.

    This endpoint trusts its inputs, so it MUST remain admin-gated. It
    exists so an administrator can exercise the group→role mapping and
    user-provisioning path end-to-end from the admin UI while the real
    SAML ACS is not yet wired up.

    A real production login flow must never use this handler; a proper
    ACS endpoint has to validate signature + NotOnOrAfter window +
    issuer + audience + replay BEFORE calling `provision_sso_user`.
    Until that exists, SSO-only logins are not possible, and this
    endpoint is a dev/admin utility, not a login primitive.
    """
    config = await load_sso_config(session)
    if not config.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SSO is not enabled. An admin must enable it in /auth/sso/config first.",
        )
    user = await provision_sso_user(
        session,
        username=body.username,
        display_name=body.display_name,
        groups=body.groups,
        config=config,
    )
    await session.flush()
    token = create_jwt(user, secret=settings.bearer_token)
    _audit(
        session,
        actor=principal.username,
        action="sso_assertion_test",
        target=user.id,
        details={"groups": body.groups, "assigned_role": user.role, "for_user": user.username},
    )
    await session.commit()
    return LoginResponse(
        token=token,
        user={
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "display_name": user.display_name,
        },
    )
