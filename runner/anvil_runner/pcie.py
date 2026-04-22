"""Parse PCIe link capability and current state for NVMe devices.

For every NVMe controller we read /sys/class/nvme/<name>/address to get its
PCIe BDF (bus:dev.func), then run `lspci -vvv -s <bdf>` in the host mount
namespace to get the Linux-formatted capability dump. We extract:

    LnkCap:  what the device + slot combination is capable of
             (e.g. "Speed 16GT/s, Width x4")
    LnkSta:  what the link is currently running at
             (e.g. "Speed 8GT/s (downgraded), Width x4 (ok)")
    LnkCap2: supported link speeds enum (e.g. "2.5-32GT/s")
    LnkSta2: per-lane equalization / de-emphasis info

The UI flags a device as "link-degraded" when current speed_gt < max_gt or
current width < max_width. This is exactly the "device supports PCIe 5.0
x4 but the test is running at PCIe 4.0 x4" flag the user asked for.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from anvil_runner.discovery import _run_host

_SPEED_RE = re.compile(r"Speed\s+([\d.]+)GT/s")
_WIDTH_RE = re.compile(r"Width\s+x(\d+)")
_LNK_STA_DEGRADED_RE = re.compile(r"\(downgraded\)")
_LNK_STA_WIDTH_DEGRADED_RE = re.compile(r"Width\s+x\d+\s+\(downgraded\)")


def _host_path(p: str) -> str:
    root = Path("/proc/1/root")
    if root.exists():
        return str(root) + p
    return p


def _read(path: str) -> str | None:
    try:
        with open(_host_path(path)) as f:
            return f.read().strip()
    except (OSError, PermissionError):
        return None


def _parse_speed_gt(text: str) -> float | None:
    m = _SPEED_RE.search(text)
    return float(m.group(1)) if m else None


def _parse_width(text: str) -> int | None:
    m = _WIDTH_RE.search(text)
    return int(m.group(1)) if m else None


def _gt_to_pcie_gen(speed_gt: float) -> str:
    if speed_gt >= 63:
        return "Gen6"
    if speed_gt >= 31:
        return "Gen5"
    if speed_gt >= 15:
        return "Gen4"
    if speed_gt >= 7:
        return "Gen3"
    if speed_gt >= 4:
        return "Gen2"
    if speed_gt >= 2:
        return "Gen1"
    return f"{speed_gt}GT/s"


async def probe_pcie_link(address: str) -> dict[str, Any] | None:
    """Return {capability: {...}, status: {...}, degraded: bool, ...} for one BDF.

    Returns None if lspci didn't find the address or the output had no Link
    capability section (e.g. the device sits behind a non-PCIe bridge).
    """
    rc, out, _ = await _run_host("lspci", "-vvv", "-s", address, timeout=10.0)
    if rc != 0 or not out:
        return None

    cap_line = status_line = cap2_line = status2_line = None
    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("LnkCap:"):
            cap_line = line[len("LnkCap:"):].strip()
        elif line.startswith("LnkSta:"):
            status_line = line[len("LnkSta:"):].strip()
        elif line.startswith("LnkCap2:"):
            cap2_line = line[len("LnkCap2:"):].strip()
        elif line.startswith("LnkSta2:"):
            status2_line = line[len("LnkSta2:"):].strip()

    if cap_line is None and status_line is None:
        return None

    cap_speed = _parse_speed_gt(cap_line or "")
    cap_width = _parse_width(cap_line or "")
    cur_speed = _parse_speed_gt(status_line or "")
    cur_width = _parse_width(status_line or "")

    speed_degraded = (
        cap_speed is not None and cur_speed is not None and cur_speed < cap_speed
    ) or bool(_LNK_STA_DEGRADED_RE.search(status_line or ""))
    width_degraded = (
        cap_width is not None and cur_width is not None and cur_width < cap_width
    ) or bool(_LNK_STA_WIDTH_DEGRADED_RE.search(status_line or ""))
    degraded = speed_degraded or width_degraded

    return {
        "address": address,
        "capability": {
            "raw": cap_line,
            "speed_gt": cap_speed,
            "width": cap_width,
            "pcie_gen": _gt_to_pcie_gen(cap_speed) if cap_speed else None,
        },
        "status": {
            "raw": status_line,
            "speed_gt": cur_speed,
            "width": cur_width,
            "pcie_gen": _gt_to_pcie_gen(cur_speed) if cur_speed else None,
        },
        "capability_raw_2": cap2_line,
        "status_raw_2": status2_line,
        "degraded": degraded,
        "speed_degraded": speed_degraded,
        "width_degraded": width_degraded,
    }


async def probe_nvme_pcie(nvme_controller: str) -> dict[str, Any] | None:
    """nvme_controller: 'nvme0' (no leading /dev/)."""
    addr = _read(f"/sys/class/nvme/{nvme_controller}/address")
    if not addr:
        return None
    return await probe_pcie_link(addr)
