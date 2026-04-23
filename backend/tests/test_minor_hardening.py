from __future__ import annotations

import bcrypt
from httpx import AsyncClient

from anvil import db as anvil_db
from anvil.models import Device, Run, RunStatus, User, UserRole


async def _seed_device_and_run(dev_id: str = "d1", run_id: str = "r1") -> None:
    async with anvil_db.get_sessionmaker()() as session:
        session.add(Device(
            id=dev_id,
            fingerprint=f"fp-{dev_id}",
            model="M",
            serial="SER12345",
            brand="B",
            protocol="nvme",
            current_device_path="/dev/x",
            metadata_json={},
        ))
        session.add(Run(
            id=run_id,
            device_id=dev_id,
            profile_name="snia_quick_pts",
            profile_snapshot={},
            status=RunStatus.COMPLETE.value,
            device_path_at_run="/dev/x",
        ))
        await session.commit()


async def _seed_user(username: str, role: str) -> None:
    import ulid
    async with anvil_db.get_sessionmaker()() as session:
        session.add(User(
            id=str(ulid.ULID()),
            username=username,
            password_hash=bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4)).decode(),
            role=role,
            is_active=True,
        ))
        await session.commit()


async def _token(client: AsyncClient, username: str) -> str:
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "pw"},
        headers={"Authorization": ""},
    )
    assert r.status_code == 200
    return r.json()["token"]


async def test_viewer_cannot_see_share_slug(app_client: AsyncClient) -> None:
    await _seed_device_and_run()
    await _seed_user("v1", UserRole.VIEWER.value)

    r = await app_client.post("/api/runs/r1/share")
    assert r.status_code == 200
    real_slug = r.json()["share_slug"]

    viewer_tok = await _token(app_client, "v1")

    r2 = await app_client.get(
        "/api/runs/r1/share",
        headers={"Authorization": f"Bearer {viewer_tok}"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert "share_slug" not in body
    assert body["is_shared"] is True

    r3 = await app_client.get("/api/runs/r1/share")
    body3 = r3.json()
    assert body3["share_slug"] == real_slug
    assert body3["is_shared"] is True


async def test_sso_config_optimistic_locking(app_client: AsyncClient) -> None:
    r = await app_client.get("/api/auth/sso/config")
    assert r.status_code == 200
    version_0 = r.json()["version"]

    body1 = {
        "enabled": True,
        "idp_metadata_url": "https://idp/metadata",
        "idp_entity_id": "idp",
        "sp_entity_id": "anvil",
        "sp_acs_url": "https://anvil/acs",
        "username_attribute": "uid",
        "display_name_attribute": "displayName",
        "email_attribute": "mail",
        "groups_attribute": "memberOf",
        "default_role": "viewer",
        "mappings": [],
        "expected_version": version_0,
    }
    r1 = await app_client.put("/api/auth/sso/config", json=body1)
    assert r1.status_code == 200
    version_1 = r1.json()["version"]
    assert version_1 is not None and version_1 != version_0

    body_stale = dict(body1)
    body_stale["expected_version"] = version_0
    body_stale["idp_metadata_url"] = "https://idp/conflict"
    r_conflict = await app_client.put("/api/auth/sso/config", json=body_stale)
    assert r_conflict.status_code == 409

    body_fresh = dict(body1)
    body_fresh["expected_version"] = version_1
    body_fresh["idp_metadata_url"] = "https://idp/winner"
    r_ok = await app_client.put("/api/auth/sso/config", json=body_fresh)
    assert r_ok.status_code == 200
    assert r_ok.json()["idp_metadata_url"] == "https://idp/winner"


async def test_sso_config_first_write_without_version_allowed(
    app_client: AsyncClient,
) -> None:
    body = {
        "enabled": False,
        "idp_metadata_url": "",
        "idp_entity_id": "",
        "sp_entity_id": "anvil",
        "sp_acs_url": "",
        "username_attribute": "uid",
        "display_name_attribute": "displayName",
        "email_attribute": "mail",
        "groups_attribute": "memberOf",
        "default_role": "viewer",
        "mappings": [],
    }
    r = await app_client.put("/api/auth/sso/config", json=body)
    assert r.status_code == 200
    assert r.json()["version"] is not None
