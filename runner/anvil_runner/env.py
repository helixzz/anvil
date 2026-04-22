from __future__ import annotations

import asyncio
import contextlib
import glob
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from anvil_runner.discovery import _read_host_proc_lines, _run_host

log = structlog.get_logger("anvil_runner.env")

Severity = str


@dataclass
class Check:
    category: str
    name: str
    severity: Severity
    value: str | None
    status: str
    expected: str | None = None
    remediation: str | None = None
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "severity": self.severity,
            "value": self.value,
            "status": self.status,
            "expected": self.expected,
            "remediation": self.remediation,
            "details": self.details,
        }


def _host_path(path: str) -> str:
    """Translate a /proc or /sys path to the /proc/1/root/... equivalent when running
    inside a container. The runner declares pid=host so /proc/1/root is the host rootfs.
    On a bare-metal dev host /proc/1/root === /, so this is a no-op in that case.
    """
    root = Path("/proc/1/root")
    if root.exists():
        return str(root) + path
    return path


def _read_one(path: str) -> str | None:
    with contextlib.suppress(OSError):
        with open(_host_path(path)) as f:
            return f.read().strip()
    return None


def _glob_paths(pattern: str) -> list[str]:
    return sorted(glob.glob(_host_path(pattern)))


async def _cpu_checks() -> list[Check]:
    out: list[Check] = []
    governors: list[str] = []
    for p in _glob_paths("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"):
        with contextlib.suppress(OSError):
            with open(p) as f:
                governors.append(f.read().strip())
    if governors:
        unique = sorted(set(governors))
        value = ", ".join(unique)
        all_perf = unique == ["performance"]
        out.append(
            Check(
                category="cpu",
                name="scaling_governor",
                severity="critical",
                value=value,
                status="pass" if all_perf else "warn",
                expected="performance",
                remediation=(
                    "echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
                    if not all_perf else None
                ),
                details={"cores_checked": len(governors), "distribution": {g: governors.count(g) for g in unique}},
            )
        )

    no_turbo = _read_one("/sys/devices/system/cpu/intel_pstate/no_turbo")
    boost = _read_one("/sys/devices/system/cpu/cpufreq/boost")
    if no_turbo is not None:
        out.append(
            Check(
                category="cpu",
                name="turbo_boost",
                severity="info",
                value="disabled" if no_turbo == "1" else "enabled",
                status="info",
                expected="either; document the state",
                details={"intel_pstate_no_turbo": no_turbo},
            )
        )
    elif boost is not None:
        out.append(
            Check(
                category="cpu",
                name="cpu_boost",
                severity="info",
                value="enabled" if boost == "1" else "disabled",
                status="info",
                expected="either; document the state",
                details={"cpufreq_boost": boost},
            )
        )

    min_freq_khz: list[int] = []
    max_freq_khz: list[int] = []
    cur_freq_khz: list[int] = []
    for cpu_dir in _glob_paths("/sys/devices/system/cpu/cpu[0-9]*/cpufreq"):
        for field, collector in (("scaling_min_freq", min_freq_khz),
                                  ("scaling_max_freq", max_freq_khz),
                                  ("scaling_cur_freq", cur_freq_khz)):
            v = _read_one(f"{cpu_dir[len(str(Path('/proc/1/root'))):] if cpu_dir.startswith(str(Path('/proc/1/root'))) else cpu_dir}/{field}")
            if v:
                with contextlib.suppress(ValueError):
                    collector.append(int(v))
    if cur_freq_khz and max_freq_khz:
        avg_cur = sum(cur_freq_khz) / len(cur_freq_khz) / 1000
        max_max = max(max_freq_khz) / 1000
        pinned = avg_cur >= max_max * 0.95
        out.append(
            Check(
                category="cpu",
                name="frequency_pin",
                severity="warning",
                value=f"{avg_cur:.0f} MHz avg / {max_max:.0f} MHz max",
                status="pass" if pinned else "warn",
                expected="avg ≈ max (within 5 %)",
                details={"avg_current_mhz": avg_cur, "max_mhz": max_max},
            )
        )

    smt_active = _read_one("/sys/devices/system/cpu/smt/active")
    if smt_active is not None:
        out.append(
            Check(
                category="cpu",
                name="smt_state",
                severity="info",
                value="on" if smt_active == "1" else "off",
                status="info",
                expected="document the state",
            )
        )

    return out


async def _pcie_checks() -> list[Check]:
    out: list[Check] = []
    policy = _read_one("/sys/module/pcie_aspm/parameters/policy")
    if policy:
        current = policy
        match = re.search(r"\[([^]]+)\]", policy)
        if match:
            current = match.group(1)
        is_perf = current == "performance"
        out.append(
            Check(
                category="pcie",
                name="aspm_policy",
                severity="critical",
                value=current,
                status="pass" if is_perf else "warn",
                expected="performance",
                remediation=(
                    "echo performance | sudo tee /sys/module/pcie_aspm/parameters/policy"
                    if not is_perf else None
                ),
                details={"raw": policy},
            )
        )
    return out


async def _nvme_checks() -> list[Check]:
    out: list[Check] = []
    for ns_dir in _glob_paths("/sys/class/nvme/nvme[0-9]*"):
        name = os.path.basename(ns_dir)
        current_pstate = _read_one(f"/sys/class/nvme/{name}/cntrltype") or None
        out.append(
            Check(
                category="nvme",
                name=f"{name}_present",
                severity="info",
                value=current_pstate or "present",
                status="info",
            )
        )
    default_ps = _read_one("/sys/module/nvme_core/parameters/default_ps_max_latency_us")
    if default_ps is not None:
        is_zero = default_ps.strip() == "0"
        out.append(
            Check(
                category="nvme",
                name="default_ps_max_latency_us",
                severity="warning",
                value=default_ps,
                status="pass" if is_zero else "warn",
                expected="0 (APST disabled for reproducibility)",
                remediation=(
                    "Add nvme_core.default_ps_max_latency_us=0 to kernel cmdline"
                    if not is_zero else None
                ),
            )
        )
    return out


async def _block_checks() -> list[Check]:
    out: list[Check] = []
    for dev_dir in _glob_paths("/sys/block/nvme[0-9]*n[0-9]*"):
        name = os.path.basename(dev_dir)
        sched = _read_one(f"/sys/block/{name}/queue/scheduler")
        if sched:
            match = re.search(r"\[([^]]+)\]", sched)
            current = match.group(1) if match else sched
            is_none = current == "none"
            out.append(
                Check(
                    category="block",
                    name=f"{name}_scheduler",
                    severity="warning",
                    value=current,
                    status="pass" if is_none else "warn",
                    expected="none",
                    remediation=(
                        f"echo none | sudo tee /sys/block/{name}/queue/scheduler"
                        if not is_none else None
                    ),
                    details={"options": sched},
                )
            )
        nr = _read_one(f"/sys/block/{name}/queue/nr_requests")
        if nr:
            with contextlib.suppress(ValueError):
                out.append(
                    Check(
                        category="block",
                        name=f"{name}_nr_requests",
                        severity="info",
                        value=nr,
                        status="info" if int(nr) >= 1024 else "warn",
                        expected=">= 1024",
                    )
                )
    return out


async def _load_checks() -> list[Check]:
    out: list[Check] = []
    try:
        la = (_read_one("/proc/loadavg") or "0 0 0").split()
        la1 = float(la[0])
    except (ValueError, IndexError):
        la1 = 0.0
    ncpus = len(_glob_paths("/sys/devices/system/cpu/cpu[0-9]*"))
    load_per_cpu = la1 / max(ncpus, 1)
    out.append(
        Check(
            category="load",
            name="loadavg_1min",
            severity="warning",
            value=f"{la1:.2f} ({load_per_cpu*100:.1f}% of {ncpus} cpus)",
            status="pass" if load_per_cpu < 0.05 else "warn",
            expected="< 5 % of cpus",
            details={"la1": la1, "ncpus": ncpus},
        )
    )

    swaps = [line for line in _read_host_proc_lines("swaps") if line and not line.startswith("Filename")]
    out.append(
        Check(
            category="load",
            name="swap_active",
            severity="info",
            value=f"{len(swaps)} swap area(s)",
            status="info",
            details={"entries": swaps[:3]},
        )
    )

    rc, out_vmstat, _ = await _run_host("cat", "/proc/vmstat")
    pswpin = pswpout = None
    if rc == 0:
        for line in out_vmstat.splitlines():
            if line.startswith("pswpin "):
                with contextlib.suppress(ValueError):
                    pswpin = int(line.split()[1])
            elif line.startswith("pswpout "):
                with contextlib.suppress(ValueError):
                    pswpout = int(line.split()[1])
    if pswpin is not None and pswpout is not None:
        paging = pswpin + pswpout
        out.append(
            Check(
                category="load",
                name="swap_page_activity",
                severity="info",
                value=f"in={pswpin} out={pswpout}",
                status="info",
                details={"pswpin": pswpin, "pswpout": pswpout, "total": paging},
            )
        )

    return out


async def _tools_checks() -> list[Check]:
    out: list[Check] = []
    for cmd, name in (("fio", "fio"), ("nvme", "nvme_cli"), ("smartctl", "smartctl")):
        rc, version_out, _ = await _run_host(cmd, "--version")
        if rc == 0:
            first_line = version_out.splitlines()[0] if version_out else ""
            out.append(
                Check(
                    category="tools",
                    name=name,
                    severity="info",
                    value=first_line[:120],
                    status="pass",
                )
            )
        else:
            out.append(
                Check(
                    category="tools",
                    name=name,
                    severity="critical",
                    value="not found",
                    status="fail",
                    expected="present",
                )
            )

    kernel = _read_one("/proc/version")
    if kernel:
        out.append(
            Check(
                category="tools",
                name="kernel",
                severity="info",
                value=kernel[:120],
                status="info",
            )
        )
    return out


async def environment_report() -> list[dict[str, Any]]:
    groups = await asyncio.gather(
        _cpu_checks(),
        _pcie_checks(),
        _nvme_checks(),
        _block_checks(),
        _load_checks(),
        _tools_checks(),
        return_exceptions=True,
    )
    flat: list[Check] = []
    for g in groups:
        if isinstance(g, list):
            flat.extend(g)
        else:
            log.warning("env_group_failed", error=repr(g))
    return [c.as_dict() for c in flat]
