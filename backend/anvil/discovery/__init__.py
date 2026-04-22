from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anvil.logging import get_logger

log = get_logger("anvil.discovery")


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

    @property
    def fingerprint(self) -> str:
        material = self.wwid or f"{self.model}|{self.serial}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


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
    return proc.returncode or 0, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")


async def _root_source() -> str | None:
    rc, out, _ = await _run_cmd("findmnt", "-n", "-o", "SOURCE", "/")
    if rc != 0:
        return None
    src = out.strip()
    if not src:
        return None
    with contextlib.suppress(OSError):
        src = str(Path(src).resolve())
    return src


async def _parent_kname_for(src: str) -> str | None:
    rc, out, _ = await _run_cmd("lsblk", "-ndo", "PKNAME", src)
    if rc != 0:
        return None
    parent = out.strip()
    return parent or None


async def _holders_for(kname: str) -> set[str]:
    """Walk /sys/block/<kname>/holders/ to find all devices whose backing includes this one."""
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
    try:
        with open("/proc/swaps") as f:
            for idx, line in enumerate(f):
                if idx == 0:
                    continue
                parts = line.split()
                if parts:
                    sources.add(parts[0])
    except FileNotFoundError:
        return sources
    return sources


async def _mount_sources() -> set[str]:
    sources: set[str] = set()
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if parts:
                    sources.add(parts[0])
    except FileNotFoundError:
        return sources
    return sources


def _read_sysfs_int(path: str) -> int | None:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


async def _lsblk_tree() -> dict[str, Any]:
    rc, out, err = await _run_cmd(
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
    rc, out, _ = await _run_cmd("nvme", "list", "-o", "json")
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


async def _collect_exclusions() -> tuple[set[str], set[str]]:
    """Return (kname-set, source-set) of all devices that must not be touched.

    Walks the root FS holder chain, swap sources, and all mounted FS sources.
    Expands each into a parent kname via lsblk when possible.
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

        is_testable = True
        exclusion_reason: str | None = None

        if kname in excluded_knames:
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

        if is_testable:
            for child in children:
                if child.get("mountpoint") or (child.get("mountpoints") or [None])[0]:
                    is_testable = False
                    exclusion_reason = f"partition {child.get('path')} is mounted"
                    break

        holders_path = Path(f"/sys/block/{kname}/holders")
        if is_testable and holders_path.exists():
            holders = [h.name for h in holders_path.iterdir()]
            if holders:
                is_testable = False
                exclusion_reason = f"has active holders: {', '.join(holders)}"

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
            )
        )

    return discovered
