"""Profile Compare aggregates by product model (median of per-drive medians)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from anvil import db as anvil_db
from anvil.models import Device, Run, RunPhase, RunStatus

PHASE = "rnd_4k_q32t1_read"  # parsed as generic / 4k / qd32 / t1 / read


async def _seed(drives: dict[str, tuple[str, str | None, list[float]]]) -> None:
    """drives: device_id -> (model, firmware, read_iops per complete run)."""
    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    async with anvil_db.session_scope() as s:
        for did, (model, fw, iops_runs) in drives.items():
            s.add(Device(id=did, fingerprint=f"fp-{did}", model=model, serial=f"SN-{did}",
                         firmware=fw, vendor=None, protocol="nvme", is_testable=True,
                         metadata_json={}))
            await s.flush()
            for i, iops in enumerate(iops_runs):
                rid = f"{did}-r{i}"
                s.add(Run(id=rid, device_id=did, profile_name="quick", profile_snapshot={},
                          status=RunStatus.COMPLETE.value, device_path_at_run="/dev/x",
                          queued_at=t0 + timedelta(hours=i), finished_at=t0 + timedelta(hours=i)))
                await s.flush()
                s.add(RunPhase(id=f"{rid}-p", run_id=rid, phase_order=0, phase_name=PHASE,
                               pattern="randread", block_size=4096, iodepth=32, numjobs=1,
                               rwmix_write_pct=0, runtime_s=20, read_iops=iops))
        # a failed run must never count
        s.add(Run(id="bad", device_id="a1", profile_name="quick", profile_snapshot={},
                  status=RunStatus.FAILED.value, device_path_at_run="/dev/x", queued_at=t0))


def _point(series: dict) -> dict:
    (pt,) = [p for p in series["points"] if p["raw_name"] == PHASE]
    return pt


async def test_model_series_is_median_of_per_drive_medians(app_client: AsyncClient) -> None:
    await _seed({
        # drive a1 ran 3x (median 100); a2 once (200); a3 once (400) -> model median 200,
        # not the plain mean/median over all 5 runs.
        "a1": ("ALPHA X1", "FW1", [90, 100, 1000]),
        "a2": ("ALPHA X1", "FW1", [200]),
        "a3": ("ALPHA X1", "FW2", [400]),
        "b1": ("BETA Y2", "FW9", [50]),
    })
    cand = (await app_client.get("/api/profile-compare/candidates",
                                 params={"profile_name": "quick"})).json()
    by_model = {m["model"]: m for m in cand["models"]}
    assert by_model["ALPHA X1"]["unit_count"] == 3
    assert by_model["ALPHA X1"]["run_count"] == 5
    assert by_model["ALPHA X1"]["firmwares"] == ["FW1", "FW2"]
    slugs = [by_model["ALPHA X1"]["model_slug"], by_model["BETA Y2"]["model_slug"]]

    r = await app_client.get("/api/profile-compare",
                             params={"profile_name": "quick", "model_slugs": ",".join(slugs)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["group_by"] == "model"
    alpha, beta = body["series"]
    assert (alpha["kind"], alpha["unit_count"], alpha["run_count"]) == ("model", 3, 5)
    assert [u["serial"] for u in alpha["units"]] == ["SN-a1", "SN-a2", "SN-a3"]
    pt = _point(alpha)
    assert pt["read_iops"] == 200
    assert pt["spread"]["read_iops"] == {"min": 100, "max": 400, "n": 3}  # drive-to-drive
    assert pt["bs_label"] == "4k" and pt["qd"] == 32
    assert _point(beta)["read_iops"] == 50


async def test_device_series_uses_all_complete_runs(app_client: AsyncClient) -> None:
    await _seed({"a1": ("ALPHA X1", "FW1", [90, 100, 1000]), "b1": ("BETA Y2", None, [50])})
    body = (await app_client.get("/api/profile-compare",
                                 params={"profile_name": "quick", "device_ids": "a1,b1"})).json()
    a1 = body["series"][0]
    assert (a1["kind"], a1["run_count"], a1["serial"]) == ("device", 3, "SN-a1")
    pt = _point(a1)
    assert pt["read_iops"] == 100
    assert pt["spread"]["read_iops"] == {"min": 90, "max": 1000, "n": 3}  # run-to-run


async def test_profile_compare_requires_exactly_one_selector(app_client: AsyncClient) -> None:
    for params in ({"profile_name": "quick"},
                   {"profile_name": "quick", "device_ids": "a", "model_slugs": "b"}):
        assert (await app_client.get("/api/profile-compare", params=params)).status_code == 400
    empty = (await app_client.get("/api/profile-compare/candidates",
                                  params={"profile_name": "nothing"})).json()
    assert empty["models"] == [] and empty["devices"] == []
