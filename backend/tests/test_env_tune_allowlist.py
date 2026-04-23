from __future__ import annotations

import sys
from pathlib import Path

RUNNER_ROOT = Path(__file__).resolve().parents[2] / "runner"
if str(RUNNER_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNNER_ROOT))

import pytest  # noqa: E402
from anvil_runner.env_tune import _path_is_tunable, _write_sysfs  # noqa: E402


def test_allowlist_accepts_cpu_governor() -> None:
    assert _path_is_tunable("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    assert _path_is_tunable("/sys/devices/system/cpu/cpu127/cpufreq/scaling_governor")


def test_allowlist_accepts_nvme_block_paths() -> None:
    assert _path_is_tunable("/sys/block/nvme0n1/queue/scheduler")
    assert _path_is_tunable("/sys/block/nvme3n2/queue/nr_requests")
    assert _path_is_tunable("/sys/block/nvme0n1/queue/read_ahead_kb")


def test_allowlist_accepts_pcie_aspm() -> None:
    assert _path_is_tunable("/sys/module/pcie_aspm/parameters/policy")


def test_allowlist_rejects_etc_passwd() -> None:
    assert not _path_is_tunable("/etc/passwd")


def test_allowlist_rejects_proc_sysrq() -> None:
    assert not _path_is_tunable("/proc/sysrq-trigger")


def test_allowlist_rejects_path_traversal() -> None:
    assert not _path_is_tunable("/sys/block/nvme0n1/queue/../../../etc/passwd")
    assert not _path_is_tunable("/sys/block/../../../etc/shadow")


def test_allowlist_rejects_empty_and_none_paths() -> None:
    assert not _path_is_tunable("")
    assert not _path_is_tunable("../../../etc/passwd")


def test_write_sysfs_refuses_unallowed_path(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.write_text("orig")
    with pytest.raises(PermissionError):
        _write_sysfs(str(bad), "evil")
    assert bad.read_text() == "orig"
