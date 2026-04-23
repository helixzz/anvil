"""SSO integration points for Anvil.

This module defines the storage model + admin-configurable settings +
interactive group→role mapping for a single-tenant, SAML-first SSO flow.

Design

- A single `sso_config` JSONB row (stored in a new `app_settings` table so
  multi-key config can share it) records the IdP metadata URL or inlined
  XML, the IdP entity ID, the Anvil SP entity ID, the Anvil SP ACS URL,
  whether SSO is enabled, and the group→role mapping.
- `resolve_sso_role(groups)` takes the list of group names the IdP
  asserted about a user and returns the highest matching Anvil role, or
  a configured default role for users with no matching group.
- `provision_sso_user(username, email, display_name, groups)` creates
  or updates a User row, sets the role from the mapping, and returns
  the (user, role) pair — ready to be turned into a JWT by the caller.
- No cryptographic SAML validation is performed here; the actual IdP
  integration (signed AuthnResponse parsing, assertion decryption,
  clock-skew tolerance, replay protection via NotOnOrAfter) is the
  caller's responsibility. This module handles only Anvil-side state +
  policy.

Why split this way

The user requirement is "reserve the capability, with interactive admin
configuration". A typical lab will point Anvil at a corporate IdP (AD
FS, Okta, Keycloak, Azure AD) whose metadata is a moving target and
whose crypto libraries change every year. Keeping the policy layer
separate from whichever library actually parses `<saml:AuthnResponse>`
lets the integration cycle independently of a long-lived policy layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import ulid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anvil.models import AppSetting, User, UserRole

SSO_CONFIG_KEY = "sso"


@dataclass
class GroupRoleMapping:
    """Admin-configurable rule: if the IdP asserts this group, grant this role."""

    group: str
    role: str

    def as_dict(self) -> dict[str, Any]:
        return {"group": self.group, "role": self.role}


@dataclass
class SsoConfig:
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
    mappings: list[GroupRoleMapping] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SsoConfig:
        data = data or {}
        mappings = [
            GroupRoleMapping(group=m.get("group", ""), role=m.get("role", UserRole.VIEWER.value))
            for m in (data.get("mappings") or [])
            if m.get("group")
        ]
        return cls(
            enabled=bool(data.get("enabled", False)),
            idp_metadata_url=str(data.get("idp_metadata_url", "")),
            idp_entity_id=str(data.get("idp_entity_id", "")),
            sp_entity_id=str(data.get("sp_entity_id", "anvil")),
            sp_acs_url=str(data.get("sp_acs_url", "")),
            username_attribute=str(data.get("username_attribute", "uid")),
            display_name_attribute=str(data.get("display_name_attribute", "displayName")),
            email_attribute=str(data.get("email_attribute", "mail")),
            groups_attribute=str(data.get("groups_attribute", "memberOf")),
            default_role=str(data.get("default_role", UserRole.VIEWER.value)),
            mappings=mappings,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "idp_metadata_url": self.idp_metadata_url,
            "idp_entity_id": self.idp_entity_id,
            "sp_entity_id": self.sp_entity_id,
            "sp_acs_url": self.sp_acs_url,
            "username_attribute": self.username_attribute,
            "display_name_attribute": self.display_name_attribute,
            "email_attribute": self.email_attribute,
            "groups_attribute": self.groups_attribute,
            "default_role": self.default_role,
            "mappings": [m.as_dict() for m in self.mappings],
        }


ROLE_RANK = {
    UserRole.VIEWER.value: 1,
    UserRole.OPERATOR.value: 2,
    UserRole.ADMIN.value: 3,
}


def resolve_sso_role(config: SsoConfig, groups: list[str]) -> str:
    """Walk the mappings in declaration order; every mapping whose group name
    appears in the IdP-asserted groups contributes a candidate role. Return
    the highest-ranked candidate (admin > operator > viewer). If no mapping
    matches, return the config's default_role.
    """
    candidates = [m.role for m in config.mappings if m.group in groups]
    if not candidates:
        return config.default_role
    return max(candidates, key=lambda r: ROLE_RANK.get(r, 0))


async def load_sso_config(session: AsyncSession) -> SsoConfig:
    result = await session.execute(select(AppSetting).where(AppSetting.key == SSO_CONFIG_KEY))
    row = result.scalar_one_or_none()
    if row is None:
        return SsoConfig()
    return SsoConfig.from_dict(row.value)


async def load_sso_config_with_version(
    session: AsyncSession,
) -> tuple[SsoConfig, str | None]:
    """Return (config, version) where version is an ISO8601 updated_at.

    Admin clients should pass this version back on PUT to detect
    concurrent edits. A None version means the row does not yet exist.
    """
    result = await session.execute(select(AppSetting).where(AppSetting.key == SSO_CONFIG_KEY))
    row = result.scalar_one_or_none()
    if row is None:
        return (SsoConfig(), None)
    return (SsoConfig.from_dict(row.value), row.updated_at.isoformat())


class SsoConfigVersionConflict(RuntimeError):
    """Raised when a PUT attempts to overwrite a newer app_settings row."""


class _Unset:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<UNSET>"


_UNSET = _Unset()


async def save_sso_config(
    session: AsyncSession,
    config: SsoConfig,
    expected_version: str | None | _Unset = _UNSET,
) -> str:
    """Persist the SSO config; returns the new version (updated_at ISO).

    Semantics of `expected_version`:
      - omitted (default `_UNSET`): force-save, skip the check. Used
        only by internal tooling / migrations.
      - `None`: the caller expects no row to exist yet (first save);
        if a row DOES exist, a `SsoConfigVersionConflict` is raised.
      - string: the caller expects `row.updated_at.isoformat()` to
        match; any mismatch (including a freshly-absent row) raises.
    """
    result = await session.execute(select(AppSetting).where(AppSetting.key == SSO_CONFIG_KEY))
    row = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None:
        if expected_version is not _UNSET and expected_version is not None:
            raise SsoConfigVersionConflict(
                f"SSO config does not exist but caller expected version {expected_version}"
            )
        new_row = AppSetting(key=SSO_CONFIG_KEY, value=config.as_dict(), updated_at=now)
        session.add(new_row)
        await session.flush()
        await session.refresh(new_row)
        return new_row.updated_at.isoformat()
    current = row.updated_at.isoformat()
    if expected_version is not _UNSET and expected_version != current:
        raise SsoConfigVersionConflict(
            f"version mismatch: expected {expected_version!r}, have {current!r}"
        )
    row.value = config.as_dict()
    row.updated_at = now
    await session.flush()
    await session.refresh(row)
    return row.updated_at.isoformat()


async def provision_sso_user(
    session: AsyncSession,
    *,
    username: str,
    display_name: str | None,
    groups: list[str],
    config: SsoConfig,
) -> User:
    """Ensure a User row exists for the given SSO-authenticated username and
    sync the role field from the current group mapping.

    We always re-sync role on every login: if an admin changes the mapping,
    or the IdP removes a group from the user, the change propagates on the
    next login. password_hash stays None for SSO-only users so they can't
    sign in via the username/password form.
    """
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    role = resolve_sso_role(config, groups)
    now = datetime.now(UTC)
    if user is None:
        user = User(
            id=str(ulid.ULID()),
            username=username,
            display_name=display_name,
            password_hash=None,
            role=role,
            is_active=True,
            last_login_at=now,
            metadata_json={"sso_groups": groups, "sso_provisioned": True},
        )
        session.add(user)
    else:
        user.role = role
        user.is_active = True
        user.last_login_at = now
        user.display_name = display_name or user.display_name
        md = dict(user.metadata_json or {})
        md["sso_groups"] = groups
        md["sso_last_login"] = now.isoformat()
        user.metadata_json = md
    return user
