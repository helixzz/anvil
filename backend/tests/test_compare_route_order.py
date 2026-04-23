from __future__ import annotations

from httpx import AsyncClient

from anvil import db as anvil_db
from anvil.models import Device, Run, RunPhase, RunStatus


async def _seed_two_models_with_common_phase() -> None:
    """Two devices of different models, each with a complete run that has
    the same phase name, so /compare and /common-phases both have data.
    """
    async with anvil_db.get_sessionmaker()() as session:
        for dev_id, brand, model, run_id, phase_id in [
            ("d-huawei", "Huawei", "HSSD-TEST", "r-h", "p-h"),
            ("d-samsung", "Samsung", "X4030-TEST", "r-s", "p-s"),
        ]:
            session.add(Device(
                id=dev_id,
                fingerprint=f"fp-{dev_id}",
                model=model,
                serial=f"S-{dev_id}",
                brand=brand,
                vendor=brand,
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
            session.add(RunPhase(
                id=phase_id,
                run_id=run_id,
                phase_order=0,
                phase_name="rnd_4k_q128t1_read",
                pattern="randread",
                block_size=4096,
                iodepth=128,
                numjobs=1,
                runtime_s=60,
                read_iops=100000.0,
                read_bw_bytes=400_000_000,
                read_clat_mean_ns=1000.0,
                read_clat_p99_ns=2000.0,
            ))
        await session.commit()


async def test_common_phases_returns_intersection(app_client: AsyncClient) -> None:
    await _seed_two_models_with_common_phase()
    slugs = "Huawei-HSSD-TEST,Samsung-X4030-TEST"
    r = await app_client.get(f"/api/models/compare/common-phases?slugs={slugs}")
    assert r.status_code == 200
    body = r.json()
    assert body["phase_names"] == ["rnd_4k_q128t1_read"]


async def test_compare_across_models_returns_samples(app_client: AsyncClient) -> None:
    """Regression test for the route-shadowing bug where /compare was
    being routed into /{slug} and returned 404 'Model not found'.
    """
    await _seed_two_models_with_common_phase()
    slugs = "Huawei-HSSD-TEST,Samsung-X4030-TEST"
    phase = "rnd_4k_q128t1_read"
    r = await app_client.get(
        f"/api/models/compare?slugs={slugs}&phase_name={phase}"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["phase_name"] == phase
    assert len(body["models"]) == 2
    for m in body["models"]:
        assert m["summary"]["sample_count"] == 1
        assert m["summary"]["read_iops"]["mean"] == 100000.0


async def test_compare_endpoint_does_not_collide_with_slug_route(
    app_client: AsyncClient,
) -> None:
    """Explicit guard: calling /compare without any query params must NOT
    be interpreted as model-detail with slug='compare'. It should return
    422 (missing required query param) not 404."""
    r = await app_client.get("/api/models/compare")
    assert r.status_code == 422, r.text


async def test_common_phases_endpoint_does_not_collide_with_slug_route(
    app_client: AsyncClient,
) -> None:
    r = await app_client.get("/api/models/compare/common-phases")
    assert r.status_code == 422
