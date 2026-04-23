from __future__ import annotations

import bcrypt
from httpx import AsyncClient

from anvil import db as anvil_db
from anvil.models import Device, Run, RunStatus, User, UserRole


async def _create_admin(username: str = "adm") -> str:
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


async def _create_run(status: str = RunStatus.COMPLETE.value) -> str:
    import ulid
    dev_id = str(ulid.ULID())
    run_id = str(ulid.ULID())
    async with anvil_db.get_sessionmaker()() as session:
        session.add(Device(
            id=dev_id,
            fingerprint=f"fp-{dev_id}",
            model="TestModel",
            serial="SER00001",
            brand="TestBrand",
            protocol="nvme",
            current_device_path="/dev/nvme99n1",
            metadata_json={},
        ))
        session.add(Run(
            id=run_id,
            device_id=dev_id,
            profile_name="snia_quick_pts",
            profile_snapshot={},
            status=status,
            device_path_at_run="/dev/nvme99n1",
        ))
        await session.commit()
    return run_id


async def test_sso_assertion_rejected_without_admin(app_client: AsyncClient) -> None:
    await _create_admin()
    r = await app_client.post(
        "/api/auth/sso/assertion",
        json={"username": "evil", "groups": ["admin-group"]},
        headers={"Authorization": ""},
    )
    assert r.status_code == 401


async def test_sso_assertion_rejected_with_viewer_token(app_client: AsyncClient) -> None:
    import ulid
    async with anvil_db.get_sessionmaker()() as session:
        uid = str(ulid.ULID())
        session.add(User(
            id=uid,
            username="viewer_sso",
            password_hash=bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4)).decode(),
            role=UserRole.VIEWER.value,
            is_active=True,
        ))
        await session.commit()
    r = await app_client.post(
        "/api/auth/login",
        json={"username": "viewer_sso", "password": "pw"},
        headers={"Authorization": ""},
    )
    viewer_token = r.json()["token"]

    r = await app_client.post(
        "/api/auth/sso/assertion",
        json={"username": "evil", "groups": []},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert r.status_code == 403


async def test_sso_assertion_requires_sso_enabled(app_client: AsyncClient) -> None:
    await _create_admin("adm2")
    tok = await _admin_token(app_client, "adm2")
    r = await app_client.post(
        "/api/auth/sso/assertion",
        json={"username": "test", "groups": []},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403
    assert "SSO is not enabled" in r.json()["detail"]


async def test_share_slug_generate_and_revoke(app_client: AsyncClient) -> None:
    run_id = await _create_run()

    r = await app_client.post(f"/api/runs/{run_id}/share")
    assert r.status_code == 200
    slug = r.json()["share_slug"]
    assert slug and len(slug) > 10

    r2 = await app_client.get(f"/r/runs/{slug}", headers={"Authorization": ""})
    assert r2.status_code == 200
    assert "Anvil Run Report" in r2.text

    r3 = await app_client.delete(f"/api/runs/{run_id}/share")
    assert r3.status_code == 200
    assert r3.json()["share_slug"] is None

    r4 = await app_client.get(f"/r/runs/{slug}", headers={"Authorization": ""})
    assert r4.status_code == 404


async def test_public_share_redacts_serial(app_client: AsyncClient) -> None:
    run_id = await _create_run()
    r = await app_client.post(f"/api/runs/{run_id}/share")
    slug = r.json()["share_slug"]

    pub = await app_client.get(f"/r/runs/{slug}", headers={"Authorization": ""})
    assert "SER00001" not in pub.text
    assert "0001" in pub.text


async def test_nonexistent_slug_returns_404(app_client: AsyncClient) -> None:
    r = await app_client.get("/r/runs/doesnotexist123abc", headers={"Authorization": ""})
    assert r.status_code == 404


async def test_env_tune_revert_by_receipt_id(app_client: AsyncClient) -> None:
    r = await app_client.post(
        "/api/environment/tune/revert",
        json={"receipt_id": "01NOTREAL0000000000000"},
    )
    assert r.status_code == 404


async def test_env_tune_revert_missing_body_rejected(app_client: AsyncClient) -> None:
    r = await app_client.post(
        "/api/environment/tune/revert",
        json={},
    )
    assert r.status_code == 422
