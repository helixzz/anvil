from __future__ import annotations

import bcrypt
from httpx import AsyncClient

from anvil import db as anvil_db
from anvil.models import User, UserRole


async def _create_user(username: str, role: str, password: str = "pw") -> str:
    import ulid

    async with anvil_db.get_sessionmaker()() as session:
        uid = str(ulid.ULID())
        user = User(
            id=uid,
            username=username,
            display_name=username,
            password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode(),
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
    return uid


async def _login(client: AsyncClient, username: str, password: str = "pw") -> str:
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"Authorization": ""},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


async def test_viewer_cannot_create_run(app_client: AsyncClient) -> None:
    await _create_user("viewer1", UserRole.VIEWER.value)
    token = await _login(app_client, "viewer1")

    r = await app_client.post(
        "/api/runs",
        json={"device_id": "fake", "profile_name": "snia_quick_pts"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


async def test_viewer_can_list_runs(app_client: AsyncClient) -> None:
    await _create_user("viewer2", UserRole.VIEWER.value)
    token = await _login(app_client, "viewer2")

    r = await app_client.get(
        "/api/runs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


async def test_operator_cannot_administer_users(app_client: AsyncClient) -> None:
    await _create_user("op1", UserRole.OPERATOR.value)
    token = await _login(app_client, "op1")

    r = await app_client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


async def test_admin_can_administer_users(app_client: AsyncClient) -> None:
    await _create_user("adm1", UserRole.ADMIN.value)
    token = await _login(app_client, "adm1")

    r = await app_client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


async def test_unauthenticated_rejected(app_client: AsyncClient) -> None:
    r = await app_client.get(
        "/api/runs",
        headers={"Authorization": ""},
    )
    assert r.status_code == 401


async def test_invalid_token_rejected(app_client: AsyncClient) -> None:
    r = await app_client.get(
        "/api/runs",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code in (401, 403)


async def test_login_wrong_password_rejected(app_client: AsyncClient) -> None:
    await _create_user("wrongpw", UserRole.VIEWER.value, password="correct")
    r = await app_client.post(
        "/api/auth/login",
        json={"username": "wrongpw", "password": "incorrect"},
        headers={"Authorization": ""},
    )
    assert r.status_code == 401


async def test_login_unknown_user_rejected(app_client: AsyncClient) -> None:
    r = await app_client.post(
        "/api/auth/login",
        json={"username": "nosuchuser", "password": "x"},
        headers={"Authorization": ""},
    )
    assert r.status_code == 401


async def test_inactive_user_rejected(app_client: AsyncClient) -> None:
    import ulid

    async with anvil_db.get_sessionmaker()() as session:
        user = User(
            id=str(ulid.ULID()),
            username="disabled",
            password_hash=bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4)).decode(),
            role=UserRole.ADMIN.value,
            is_active=False,
        )
        session.add(user)
        await session.commit()

    r = await app_client.post(
        "/api/auth/login",
        json={"username": "disabled", "password": "pw"},
        headers={"Authorization": ""},
    )
    assert r.status_code == 401
