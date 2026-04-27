from __future__ import annotations

import bcrypt
from httpx import AsyncClient

from anvil import db as anvil_db
from anvil.models import User, UserRole


async def _seed_admin(username: str = "adm") -> str:
    import ulid
    async with anvil_db.get_sessionmaker()() as session:
        uid = str(ulid.ULID())
        session.add(User(
            id=uid,
            username=username,
            password_hash=bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4)).decode(),
            role=UserRole.ADMIN.value,
            is_active=True,
        ))
        await session.commit()
    return uid


async def _admin_token(client: AsyncClient, username: str = "adm") -> str:
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "pw"},
        headers={"Authorization": ""},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


async def test_sso_status_returns_enabled_false_by_default(
    app_client: AsyncClient,
) -> None:
    """Without any SSO config row, status reports enabled=false."""
    r = await app_client.get("/api/auth/sso/status", headers={"Authorization": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert isinstance(body["sp_entity_id"], str)


async def test_sso_status_reflects_config(app_client: AsyncClient) -> None:
    """After an admin saves an SSO config with enabled=true, the
    status endpoint reflects it to unauthenticated callers.
    """
    await _seed_admin()
    tok = await _admin_token(app_client)
    body = {
        "enabled": True,
        "idp_metadata_url": "https://idp.example.com/metadata",
        "idp_entity_id": "https://idp.example.com/entity",
        "sp_entity_id": "anvil-lab",
            "sp_acs_url": "https://anvil.example.com",
        "username_attribute": "uid",
        "display_name_attribute": "displayName",
        "email_attribute": "mail",
        "groups_attribute": "memberOf",
        "default_role": "viewer",
        "mappings": [],
    }
    r = await app_client.put(
        "/api/auth/sso/config",
        json=body,
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200

    r2 = await app_client.get(
        "/api/auth/sso/status",
        headers={"Authorization": ""},
    )
    assert r2.status_code == 200
    status = r2.json()
    assert status["enabled"] is True
    assert status["sp_entity_id"] == "anvil-lab"


async def test_sso_login_disabled_returns_403(app_client: AsyncClient) -> None:
    r = await app_client.get(
        "/api/auth/sso/login",
        headers={"Authorization": ""},
    )
    assert r.status_code == 403
    assert "SSO is not enabled" in r.json()["detail"]


async def test_sso_metadata_returns_xml(app_client: AsyncClient) -> None:
    await _seed_admin()
    tok = await _admin_token(app_client)
    body = {
        "enabled": False,
        "idp_metadata_url": "",
        "idp_entity_id": "",
        "sp_entity_id": "anvil-test",
            "sp_acs_url": "https://anvil.example.com",
        "username_attribute": "uid",
        "display_name_attribute": "displayName",
        "email_attribute": "mail",
        "groups_attribute": "memberOf",
        "default_role": "viewer",
        "mappings": [],
    }
    r = await app_client.put(
        "/api/auth/sso/config",
        json=body,
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200

    r2 = await app_client.get(
        "/api/auth/sso/metadata",
        headers={"Authorization": ""},
    )
    assert r2.status_code == 200
    assert r2.headers["content-type"].startswith("application/xml")
    assert "<md:EntityDescriptor" in r2.text
    assert 'entityID="anvil-test"' in r2.text


async def test_sso_metadata_serialises_acs_url(app_client: AsyncClient) -> None:
    await _seed_admin()
    tok = await _admin_token(app_client)
    body = {
        "enabled": False,
        "idp_metadata_url": "",
        "idp_entity_id": "",
        "sp_entity_id": "anvil-metadata-test",
        "sp_acs_url": "https://anvil.example.com",
        "username_attribute": "uid",
        "display_name_attribute": "displayName",
        "email_attribute": "mail",
        "groups_attribute": "memberOf",
        "default_role": "viewer",
        "mappings": [],
    }
    await app_client.put(
        "/api/auth/sso/config",
        json=body,
        headers={"Authorization": f"Bearer {tok}"},
    )
    r = await app_client.get(
        "/api/auth/sso/metadata",
        headers={"Authorization": ""},
    )
    assert r.status_code == 200
    assert "https://anvil.example.com/api/auth/sso/acs" in r.text
