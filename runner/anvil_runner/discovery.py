from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger("anvil_runner.discovery")


@dataclass
class DiscoveredDevice:
    path: str
    kname: str
    model: str
    serial: str
    firmware: str | None
    wwid: str | None
    size_bytes: int
    protocol: str
    rotational: bool
    sector_size_logical: int | None
    sector_size_physical: int | None
    raw_lsblk: dict[str, Any]
    raw_nvme: dict[str, Any] | None
    is_testable: bool
    exclusion_reason: str | None
    partitions: list[str] = field(default_factory=list)
    mount_points: list[str] = field(default_factory=list)
    product_name: str = ""
    pcie: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kname": self.kname,
            "model": self.model,
            "serial": self.serial,
            "firmware": self.firmware,
            "wwid": self.wwid,
            "size_bytes": self.size_bytes,
            "protocol": self.protocol,
            "rotational": self.rotational,
            "sector_size_logical": self.sector_size_logical,
            "sector_size_physical": self.sector_size_physical,
            "raw_lsblk": self.raw_lsblk,
            "raw_nvme": self.raw_nvme,
            "is_testable": self.is_testable,
            "exclusion_reason": self.exclusion_reason,
            "partitions": self.partitions,
            "mount_points": self.mount_points,
            "product_name": self.product_name,
            "pcie": self.pcie,
        }


_HOST_NSENTER: list[str] | None = None


def _host_ns_prefix() -> list[str]:
    """Prefix subprocess calls so they run in the host's mount namespace.

    The runner container declares `pid: host`, so PID 1 is the host init. Using
    `nsenter -t 1 -m` re-enters init's mount namespace, which is the host's
    root view of `/proc/self/mounts`, `/proc/self/mountinfo`, etc. Without
    this, lsblk and findmnt inside the container see only the container's
    bind-mounts and the system-disk guard silently passes through.

    Probed lazily: if `nsenter` is unavailable or `/proc/1/ns/mnt` can't be
    opened (e.g. bare-metal dev host not running in a container at all), the
    probe returns an empty prefix, and the commands just run in the current
    namespace, which is correct for that case.
    """
    global _HOST_NSENTER
    if _HOST_NSENTER is not None:
        return _HOST_NSENTER
    self_ns = Path("/proc/self/ns/mnt")
    init_ns = Path("/proc/1/ns/mnt")
    try:
        if self_ns.is_symlink() and init_ns.is_symlink():
            if os.readlink(self_ns) == os.readlink(init_ns):
                _HOST_NSENTER = []
                return _HOST_NSENTER
    except (OSError, PermissionError):
        pass
    if Path("/proc/1/ns/mnt").is_symlink() and shutil.which("nsenter"):
        _HOST_NSENTER = ["nsenter", "-t", "1", "-m", "--"]
    else:
        _HOST_NSENTER = []
    return _HOST_NSENTER


async def _run_cmd(*args: str, timeout: float = 15.0) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return 127, "", f"{args[0]}: not found"
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        raise
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", "replace"),
        stderr.decode("utf-8", "replace"),
    )


async def _run_host(*args: str, timeout: float = 15.0) -> tuple[int, str, str]:
    """Run a command in the host mount namespace (falls back to local namespace)."""
    prefix = _host_ns_prefix()
    if not prefix:
        return await _run_cmd(*args, timeout=timeout)
    rc, out, err = await _run_cmd(*prefix, *args, timeout=timeout)
    if rc != 0 and not out:
        rc2, out2, err2 = await _run_cmd(*args, timeout=timeout)
        if rc2 == 0 or out2:
            return rc2, out2, err2
    return rc, out, err


def _read_host_proc_lines(name: str) -> list[str]:
    """Read /proc/1/<name> first (host view via pid=host), then /proc/<name>."""
    for candidate in (f"/proc/1/{name}", f"/proc/{name}"):
        try:
            with open(candidate) as f:
                return f.readlines()
        except (FileNotFoundError, PermissionError):
            continue
    return []


async def _root_source() -> str | None:
    rc, out, _ = await _run_host("findmnt", "-n", "-o", "SOURCE", "/")
    if rc != 0:
        return None
    src = out.strip()
    if not src:
        return None
    with contextlib.suppress(OSError):
        src = str(Path(src).resolve())
    return src


async def _parent_kname_for(src: str) -> str | None:
    rc, out, _ = await _run_host("lsblk", "-ndo", "PKNAME", src)
    if rc != 0:
        return None
    parent = out.strip()
    return parent or None


async def _holders_for(kname: str) -> set[str]:
    """Walk /sys/block/<kname>/holders/ to find all devices stacked on this one."""
    result: set[str] = set()
    base = Path(f"/sys/block/{kname}/holders")
    if not base.exists():
        return result
    for holder in base.iterdir():
        result.add(holder.name)
        result.update(await _holders_for(holder.name))
    return result


async def _swap_sources() -> set[str]:
    sources: set[str] = set()
    for idx, line in enumerate(_read_host_proc_lines("swaps")):
        if idx == 0:
            continue
        parts = line.split()
        if parts:
            sources.add(parts[0])
    return sources


async def _mount_sources() -> set[str]:
    sources: set[str] = set()
    for line in _read_host_proc_lines("mounts"):
        parts = line.split()
        if parts:
            sources.add(parts[0])
    return sources


async def _lsblk_tree() -> dict[str, Any]:
    rc, out, err = await _run_host(
        "lsblk",
        "-J",
        "-b",
        "-o",
        "NAME,KNAME,PATH,TYPE,SIZE,ROTA,TRAN,MODEL,SERIAL,WWN,FSTYPE,MOUNTPOINT,MOUNTPOINTS,LOG-SEC,PHY-SEC",
    )
    if rc != 0:
        log.error("lsblk_failed", err=err)
        return {"blockdevices": []}
    try:
        return json.loads(out or "{}")
    except json.JSONDecodeError as exc:
        log.error("lsblk_parse_failed", error=str(exc))
        return {"blockdevices": []}


async def _nvme_list() -> dict[str, Any]:
    rc, out, _ = await _run_host("nvme", "list", "-o", "json")
    if rc != 0:
        return {"Devices": []}
    try:
        return json.loads(out or "{}")
    except json.JSONDecodeError:
        return {"Devices": []}


def _infer_protocol(entry: dict[str, Any]) -> str:
    tran = (entry.get("tran") or "").lower()
    if tran == "nvme":
        return "nvme"
    if tran in {"sata", "sas"}:
        return tran
    if tran == "iscsi":
        return "iscsi"
    if tran == "usb":
        return "usb"
    return "unknown"


def _mountpoints_of(entry: dict[str, Any]) -> list[str]:
    """Collect every non-null mountpoint reported by lsblk for one entry.

    Modern lsblk exposes `mountpoints` (plural, may list several bind mounts)
    alongside the legacy `mountpoint` field; we merge both and dedupe while
    preserving order so the UI shows a stable list.
    """
    seen: dict[str, None] = {}
    single = entry.get("mountpoint")
    if single:
        seen[str(single)] = None
    for mp in entry.get("mountpoints") or []:
        if mp:
            seen[str(mp)] = None
    return list(seen.keys())


def _collect_mountpoints(entry: dict[str, Any]) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (disk-level-mountpoints, [(partition_path, mountpoint), ...])."""
    disk_mps = _mountpoints_of(entry)
    partition_mps: list[tuple[str, str]] = []
    for child in entry.get("children") or []:
        cpath = child.get("path") or ""
        for mp in _mountpoints_of(child):
            partition_mps.append((cpath, mp))
    return disk_mps, partition_mps
    tran = (entry.get("tran") or "").lower()
    if tran == "nvme":
        return "nvme"
    if tran in {"sata", "sas"}:
        return tran
    if tran == "iscsi":
        return "iscsi"
    if tran == "usb":
        return "usb"
    return "unknown"


async def _collect_exclusions() -> tuple[set[str], set[str]]:
    """Safety-critical: return kname-set and source-set of devices that must not be touched.

    Walks mounts, swaps, and the root FS holder chain. Expanded to include parent
    block devices of every mounted or swap source via lsblk and the sysfs holder
    graph. If any step fails the returned sets may be incomplete, so callers must
    also fall back to partition-level mountpoint checks.
    """
    excluded_knames: set[str] = set()
    sources = await _mount_sources()
    sources |= await _swap_sources()

    root_src = await _root_source()
    if root_src:
        sources.add(root_src)

    for src in list(sources):
        parent = await _parent_kname_for(src)
        if parent:
            excluded_knames.add(parent)
            excluded_knames |= await _holders_for(parent)
        basename = os.path.basename(src.rstrip("/"))
        if basename:
            excluded_knames.add(basename)
            excluded_knames |= await _holders_for(basename)

    return excluded_knames, sources


async def discover() -> list[DiscoveredDevice]:
    """Enumerate block devices and classify each as testable or excluded."""
    tree = await _lsblk_tree()
    nvme_json = await _nvme_list()
    nvme_by_path: dict[str, dict[str, Any]] = {
        str(d.get("DevicePath", "")): d for d in nvme_json.get("Devices", [])
    }
    excluded_knames, excluded_sources = await _collect_exclusions()

    discovered: list[DiscoveredDevice] = []
    for entry in tree.get("blockdevices", []):
        dtype = entry.get("type")
        if dtype != "disk":
            continue
        kname = entry.get("kname") or entry.get("name")
        path = entry.get("path") or f"/dev/{kname}"
        if not kname:
            continue

        children = entry.get("children") or []
        partition_paths = [c.get("path") for c in children if c.get("path")]
        partition_knames = {c.get("kname") for c in children if c.get("kname")}
        disk_mountpoints, partition_mountpoints = _collect_mountpoints(entry)
        all_mountpoints = list(disk_mountpoints)
        for _path, mp in partition_mountpoints:
            if mp not in all_mountpoints:
                all_mountpoints.append(mp)

        is_testable = True
        exclusion_reason: str | None = None

        if disk_mountpoints:
            is_testable = False
            exclusion_reason = (
                f"whole device is mounted at {', '.join(disk_mountpoints)}"
            )
        elif kname in excluded_knames:
            is_testable, exclusion_reason = False, "part of root FS / swap / DM stack"
        elif path in excluded_sources:
            is_testable, exclusion_reason = False, "device path is mounted or in /proc/swaps"
        else:
            for pk in partition_knames:
                if pk in excluded_knames:
                    is_testable, exclusion_reason = False, f"partition {pk} is in use"
                    break
            for pp in partition_paths:
                if pp in excluded_sources:
                    is_testable, exclusion_reason = False, f"partition {pp} is mounted"
                    break

        if is_testable and partition_mountpoints:
            first_path, first_mp = partition_mountpoints[0]
            is_testable = False
            exclusion_reason = f"partition {first_path} is mounted at {first_mp}"

        holders_path = Path(f"/sys/block/{kname}/holders")
        if is_testable and holders_path.exists():
            holders = [h.name for h in holders_path.iterdir()]
            if holders:
                is_testable = False
                exclusion_reason = f"has active holders: {', '.join(holders)}"

        if is_testable and children:
            is_testable = False
            exclusion_reason = f"has {len(children)} partition(s): {', '.join(partition_paths)}"

        if entry.get("size") in (None, 0):
            is_testable = False
            exclusion_reason = exclusion_reason or "size is zero"

        model = entry.get("model") or ""
        serial = entry.get("serial") or ""
        wwn = entry.get("wwn")
        nvme_entry = nvme_by_path.get(path)
        firmware = None
        if nvme_entry:
            firmware = nvme_entry.get("Firmware")
            model = model or nvme_entry.get("ModelNumber") or ""
            serial = serial or nvme_entry.get("SerialNumber") or ""

        if not model.strip() or not serial.strip():
            is_testable = False
            exclusion_reason = exclusion_reason or "missing model or serial"

        product_name = ""
        if nvme_entry:
            product_name = (nvme_entry.get("ProductName") or "").strip()

        pcie_info: dict[str, Any] | None = None
        if kname.startswith("nvme"):
            # Strip the namespace suffix to get the controller: nvme0n1 -> nvme0,
            # nvme12n3 -> nvme12, nvme0c0n1 (multipath) -> nvme0.
            m = re.match(r"^(nvme\d+)", kname)
            controller = m.group(1) if m else None
            if controller:
                from anvil_runner.pcie import probe_nvme_pcie
                try:
                    pcie_info = await probe_nvme_pcie(controller)
                except Exception as exc:
                    log.warning("pcie_probe_failed", kname=kname, error=str(exc))

        size_bytes = int(entry.get("size") or 0)
        rota = bool(entry.get("rota"))
        log_sec = entry.get("log-sec")
        phy_sec = entry.get("phy-sec")

        discovered.append(
            DiscoveredDevice(
                path=path,
                kname=kname,
                model=model.strip(),
                serial=serial.strip(),
                firmware=firmware,
                wwid=wwn,
                size_bytes=size_bytes,
                protocol=_infer_protocol(entry),
                rotational=rota,
                sector_size_logical=int(log_sec) if log_sec else None,
                sector_size_physical=int(phy_sec) if phy_sec else None,
                raw_lsblk=entry,
                raw_nvme=nvme_entry,
                is_testable=is_testable,
                exclusion_reason=exclusion_reason,
                partitions=partition_paths,
                mount_points=all_mountpoints,
                product_name=product_name,
                pcie=pcie_info,
            )
        )

    return discovered
