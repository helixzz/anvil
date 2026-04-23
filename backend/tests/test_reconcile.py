from __future__ import annotations

from httpx import AsyncClient

from anvil import db as anvil_db
from anvil.models import Device, Run, RunStatus
from anvil.orchestrator import reconcile_on_startup


async def _make_device(dev_id: str = "d1") -> None:
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


async def _make_run(run_id: str, status: str, dev_id: str = "d1") -> None:
    async with anvil_db.get_sessionmaker()() as session:
        session.add(Run(
            id=run_id,
            device_id=dev_id,
            profile_name="snia_quick_pts",
            profile_snapshot={},
            status=status,
            device_path_at_run="/dev/x",
        ))
        await session.commit()


async def test_reconcile_fails_stale_preflight_rows(app_client: AsyncClient) -> None:
    await _make_device()
    await _make_run("r_preflight", RunStatus.PREFLIGHT.value)
    await _make_run("r_running", RunStatus.RUNNING.value)

    requeued = await reconcile_on_startup()
    assert requeued == []

    async with anvil_db.get_sessionmaker()() as session:
        r1 = await session.get(Run, "r_preflight")
        r2 = await session.get(Run, "r_running")
        assert r1.status == RunStatus.FAILED.value
        assert r2.status == RunStatus.FAILED.value
        assert "API restarted" in r1.error_message
        assert r1.finished_at is not None


async def test_reconcile_requeues_queued_rows_in_order(app_client: AsyncClient) -> None:
    await _make_device()
    await _make_run("r_q1", RunStatus.QUEUED.value)
    await _make_run("r_q2", RunStatus.QUEUED.value)

    requeued = await reconcile_on_startup()
    assert set(requeued) == {"r_q1", "r_q2"}

    async with anvil_db.get_sessionmaker()() as session:
        r1 = await session.get(Run, "r_q1")
        r2 = await session.get(Run, "r_q2")
        assert r1.status == RunStatus.QUEUED.value
        assert r2.status == RunStatus.QUEUED.value


async def test_reconcile_leaves_complete_untouched(app_client: AsyncClient) -> None:
    await _make_device()
    await _make_run("r_done", RunStatus.COMPLETE.value)

    requeued = await reconcile_on_startup()
    assert requeued == []

    async with anvil_db.get_sessionmaker()() as session:
        r = await session.get(Run, "r_done")
        assert r.status == RunStatus.COMPLETE.value
        assert r.error_message is None


async def test_reconcile_is_idempotent(app_client: AsyncClient) -> None:
    await _make_device()
    await _make_run("r_pre", RunStatus.PREFLIGHT.value)
    await _make_run("r_q", RunStatus.QUEUED.value)

    first = await reconcile_on_startup()
    second = await reconcile_on_startup()

    assert first == ["r_q"]
    assert second == ["r_q"]

    async with anvil_db.get_sessionmaker()() as session:
        r = await session.get(Run, "r_pre")
        assert r.status == RunStatus.FAILED.value
