from __future__ import annotations

import sys
from pathlib import Path

RUNNER_ROOT = Path(__file__).resolve().parents[2] / "runner"
if str(RUNNER_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNNER_ROOT))

from unittest.mock import patch  # noqa: E402

from anvil_runner import env_tune  # noqa: E402


def test_per_key_transaction_isolates_failures(tmp_path: Path) -> None:
    """Regression: a failure in one tunable key must NOT roll back
    successful writes from other keys. This is the v1.2.3 semantic
    change — before, a single EINVAL on nvme_nr_requests would
    silently undo a full 128-CPU governor flip.
    """
    cpu0 = tmp_path / "cpu0_governor"
    cpu0.write_text("ondemand")
    cpu1 = tmp_path / "cpu1_governor"
    cpu1.write_text("ondemand")
    nvme = tmp_path / "nvme0_nr_requests"
    nvme.write_text("1023")

    fake_tunables = [
        env_tune.TuneTarget(
            key="cpu_governor",
            path_glob=str(tmp_path / "cpu*_governor"),
            desired_value="performance",
            description="",
            category="cpu",
        ),
        env_tune.TuneTarget(
            key="nvme_nr_requests",
            path_glob=str(tmp_path / "nvme*_nr_requests"),
            desired_value="2048",
            description="",
            category="block",
        ),
    ]
    fake_by_key = {t.key: t for t in fake_tunables}

    def fake_host(p: str) -> str:
        return p

    def fake_glob(pattern: str) -> list[str]:
        import glob

        return sorted(glob.glob(pattern))

    def fake_path_is_tunable(p: str) -> bool:
        return p.startswith(str(tmp_path)) and ".." not in p

    original_write = env_tune._write_sysfs

    def fake_write(path: str, value: str) -> None:
        if path.endswith("nvme0_nr_requests"):
            raise OSError(22, "Invalid argument")
        return original_write(path, value)

    with patch.object(env_tune, "TUNABLES", fake_tunables), \
         patch.object(env_tune, "TUNABLES_BY_KEY", fake_by_key), \
         patch.object(env_tune, "_host_path", fake_host), \
         patch.object(env_tune, "_glob_host", fake_glob), \
         patch.object(env_tune, "_path_is_tunable", fake_path_is_tunable), \
         patch.object(env_tune, "_write_sysfs", fake_write):
        receipt = env_tune.apply()

    assert cpu0.read_text() == "performance", "cpu_governor should NOT roll back"
    assert cpu1.read_text() == "performance", "cpu_governor should NOT roll back"
    assert nvme.read_text() == "1023", "nvme had no successful write to roll back"

    assert not receipt.reverted, "mixed outcome -> receipt.reverted must be False"
    ok = [r for r in receipt.results if r.ok]
    fail = [r for r in receipt.results if not r.ok]
    assert len(ok) == 2, "both cpu writes should be marked ok"
    assert len(fail) == 1, "the nvme write should be marked fail"
    assert fail[0].key == "nvme_nr_requests"
    assert "Invalid argument" in (fail[0].error or "")


def test_all_keys_failing_sets_reverted_true(tmp_path: Path) -> None:
    """Sanity: if literally every key fails, receipt.reverted is True."""
    nvme = tmp_path / "nvme0_nr_requests"
    nvme.write_text("1023")

    fake_tunables = [
        env_tune.TuneTarget(
            key="nvme_nr_requests",
            path_glob=str(tmp_path / "nvme*_nr_requests"),
            desired_value="2048",
            description="",
            category="block",
        ),
    ]
    fake_by_key = {t.key: t for t in fake_tunables}

    def fake_host(p: str) -> str:
        return p

    def fake_glob(pattern: str) -> list[str]:
        import glob

        return sorted(glob.glob(pattern))

    def fake_path_is_tunable(p: str) -> bool:
        return p.startswith(str(tmp_path)) and ".." not in p

    def fake_write(path: str, value: str) -> None:
        raise OSError(22, "Invalid argument")

    with patch.object(env_tune, "TUNABLES", fake_tunables), \
         patch.object(env_tune, "TUNABLES_BY_KEY", fake_by_key), \
         patch.object(env_tune, "_host_path", fake_host), \
         patch.object(env_tune, "_glob_host", fake_glob), \
         patch.object(env_tune, "_path_is_tunable", fake_path_is_tunable), \
         patch.object(env_tune, "_write_sysfs", fake_write):
        receipt = env_tune.apply()

    assert receipt.reverted is True
    assert nvme.read_text() == "1023"
    assert all(not r.ok for r in receipt.results)


def test_all_keys_succeed_leaves_reverted_false(tmp_path: Path) -> None:
    cpu = tmp_path / "cpu0_governor"
    cpu.write_text("ondemand")

    fake_tunables = [
        env_tune.TuneTarget(
            key="cpu_governor",
            path_glob=str(tmp_path / "cpu*_governor"),
            desired_value="performance",
            description="",
            category="cpu",
        ),
    ]
    fake_by_key = {t.key: t for t in fake_tunables}

    def fake_host(p: str) -> str:
        return p

    def fake_glob(pattern: str) -> list[str]:
        import glob

        return sorted(glob.glob(pattern))

    def fake_path_is_tunable(p: str) -> bool:
        return p.startswith(str(tmp_path)) and ".." not in p

    with patch.object(env_tune, "TUNABLES", fake_tunables), \
         patch.object(env_tune, "TUNABLES_BY_KEY", fake_by_key), \
         patch.object(env_tune, "_host_path", fake_host), \
         patch.object(env_tune, "_glob_host", fake_glob), \
         patch.object(env_tune, "_path_is_tunable", fake_path_is_tunable):
        receipt = env_tune.apply()

    assert receipt.reverted is False
    assert cpu.read_text() == "performance"
    assert all(r.ok for r in receipt.results)


def test_per_key_partial_failure_rolls_back_same_key_only(tmp_path: Path) -> None:
    """If a key has multiple paths and one of them fails midway, the
    other paths for THAT key get rolled back, but prior SUCCESSFUL
    keys stay tuned.
    """
    cpu_governor = tmp_path / "cpu0_governor"
    cpu_governor.write_text("ondemand")

    nvme_good = tmp_path / "nvme0_nr_requests"
    nvme_good.write_text("1023")
    nvme_bad = tmp_path / "nvme1_nr_requests_CAPPED"
    nvme_bad.write_text("1023")

    fake_tunables = [
        env_tune.TuneTarget(
            key="cpu_governor",
            path_glob=str(tmp_path / "cpu*_governor"),
            desired_value="performance",
            description="",
            category="cpu",
        ),
        env_tune.TuneTarget(
            key="nvme_nr_requests",
            path_glob=str(tmp_path / "nvme*_nr_requests*"),
            desired_value="2048",
            description="",
            category="block",
        ),
    ]
    fake_by_key = {t.key: t for t in fake_tunables}

    def fake_host(p: str) -> str:
        return p

    def fake_glob(pattern: str) -> list[str]:
        import glob

        return sorted(glob.glob(pattern))

    def fake_path_is_tunable(p: str) -> bool:
        return p.startswith(str(tmp_path)) and ".." not in p

    original_write = env_tune._write_sysfs

    def fake_write(path: str, value: str) -> None:
        if path.endswith("CAPPED"):
            raise OSError(22, "Invalid argument")
        return original_write(path, value)

    with patch.object(env_tune, "TUNABLES", fake_tunables), \
         patch.object(env_tune, "TUNABLES_BY_KEY", fake_by_key), \
         patch.object(env_tune, "_host_path", fake_host), \
         patch.object(env_tune, "_glob_host", fake_glob), \
         patch.object(env_tune, "_path_is_tunable", fake_path_is_tunable), \
         patch.object(env_tune, "_write_sysfs", fake_write):
        receipt = env_tune.apply()

    assert cpu_governor.read_text() == "performance", "cpu_governor survives"
    assert nvme_good.read_text() == "1023", "nvme_good rolled back with its key"
    assert nvme_bad.read_text() == "1023", "nvme_bad never changed"
    assert not receipt.reverted
