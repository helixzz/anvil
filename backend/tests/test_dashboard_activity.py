"""Activity timeline buckets runs by calendar day in the caller's time zone."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from httpx import AsyncClient

from anvil import db as anvil_db
from anvil.models import Device, Run, RunStatus


async def _seed(*queued_at: datetime) -> None:
    async with anvil_db.session_scope() as s:
        s.add(Device(id="dev1", fingerprint="fp1", model="M", serial="S1", protocol="nvme",
                     is_testable=True, metadata_json={}))
        await s.flush()
        for i, ts in enumerate(queued_at):
            s.add(Run(id=f"run{i}", device_id="dev1", profile_name="quick", profile_snapshot={},
                      status=RunStatus.COMPLETE.value, device_path_at_run="/dev/x", queued_at=ts))


def _counts(body: dict) -> dict[str, int]:
    return {d["day"]: d["complete"] for d in body["series"] if d["complete"]}


async def test_activity_buckets_by_local_calendar_day(app_client: AsyncClient) -> None:
    zone = ZoneInfo("Asia/Shanghai")
    today = datetime.now(zone).date()
    # 07:30 local today is 23:30 UTC *yesterday*: must count as today in UTC+8.
    early_local = datetime(today.year, today.month, today.day, 7, 30, tzinfo=zone)
    await _seed(early_local.astimezone(UTC), early_local.astimezone(UTC) - timedelta(days=2))

    local = (await app_client.get("/api/dashboard/activity",
                                  params={"days": 30, "tz": "Asia/Shanghai"})).json()
    assert local["series"][-1]["day"] == today.isoformat()
    assert _counts(local) == {
        today.isoformat(): 1,
        (today - timedelta(days=2)).isoformat(): 1,
    }

    utc = (await app_client.get("/api/dashboard/activity", params={"days": 30})).json()
    assert _counts(utc) == {
        (today - timedelta(days=1)).isoformat(): 1,
        (today - timedelta(days=3)).isoformat(): 1,
    }


async def test_activity_rejects_unknown_time_zone(app_client: AsyncClient) -> None:
    r = await app_client.get("/api/dashboard/activity", params={"tz": "Mars/Olympus"})
    assert r.status_code == 400
    r = await app_client.get("/api/dashboard/activity", params={"tz": "../etc/passwd"})
    assert r.status_code == 400
