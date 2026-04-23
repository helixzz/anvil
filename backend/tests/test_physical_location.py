from __future__ import annotations

from httpx import AsyncClient

from anvil import db as anvil_db
from anvil.models import Device


async def _seed_device(dev_id: str = "d1") -> None:
    async with anvil_db.get_sessionmaker()() as session:
        session.add(Device(
            id=dev_id,
            fingerprint=f"fp-{dev_id}",
            model="M",
            serial="S",
            brand="B",
            protocol="nvme",
            current_device_path="/dev/x",
            metadata_json={},
        ))
        await session.commit()


async def test_set_location(app_client: AsyncClient) -> None:
    await _seed_device()
    r = await app_client.patch(
        "/api/devices/d1/location",
        json={"chassis": "rack-A", "bay": "3", "tray": "front-2", "notes": "top row"},
    )
    assert r.status_code == 200
    loc = r.json()["physical_location"]
    assert loc == {"chassis": "rack-A", "bay": "3", "tray": "front-2", "notes": "top row"}


async def test_clear_location(app_client: AsyncClient) -> None:
    await _seed_device()
    await app_client.patch(
        "/api/devices/d1/location",
        json={"chassis": "rack-A", "bay": "3"},
    )
    r = await app_client.patch(
        "/api/devices/d1/location",
        json={},
    )
    assert r.status_code == 200
    assert r.json()["physical_location"] is None


async def test_location_404_for_missing_device(app_client: AsyncClient) -> None:
    r = await app_client.patch(
        "/api/devices/nosuchdevice/location",
        json={"bay": "1"},
    )
    assert r.status_code == 404


async def test_location_empty_string_treated_as_unset(app_client: AsyncClient) -> None:
    await _seed_device()
    r = await app_client.patch(
        "/api/devices/d1/location",
        json={"chassis": "rack-A", "bay": "", "tray": "", "port": ""},
    )
    assert r.status_code == 200
    assert r.json()["physical_location"] == {"chassis": "rack-A"}


async def test_device_out_includes_physical_location(app_client: AsyncClient) -> None:
    await _seed_device()
    await app_client.patch(
        "/api/devices/d1/location",
        json={"chassis": "rack-A"},
    )
    r = await app_client.get("/api/devices/d1")
    assert r.status_code == 200
    body = r.json()
    assert body["physical_location"] == {"chassis": "rack-A"}
