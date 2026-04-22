from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any


async def _run(*args: str, timeout: float = 15.0) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def nvme_identify(device_path: str) -> dict[str, Any]:
    if not shutil.which("nvme"):
        return {"error": "nvme-cli not installed"}
    rc, out, err = await _run("nvme", "id-ctrl", device_path, "-o", "json")
    if rc != 0:
        return {"error": err.strip() or f"nvme id-ctrl rc={rc}"}
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        return {"error": f"nvme id-ctrl: {exc}"}


async def nvme_smart(device_path: str) -> dict[str, Any]:
    if not shutil.which("nvme"):
        return {"error": "nvme-cli not installed"}
    rc, out, err = await _run("nvme", "smart-log", device_path, "-o", "json")
    if rc != 0:
        return {"error": err.strip() or f"nvme smart-log rc={rc}"}
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        return {"error": f"smart-log: {exc}"}


async def smartctl_all(device_path: str) -> dict[str, Any]:
    if not shutil.which("smartctl"):
        return {"error": "smartctl not installed"}
    rc, out, err = await _run("smartctl", "-j", "-a", device_path, timeout=30.0)
    if out:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            pass
    return {"error": err.strip() or f"smartctl rc={rc}"}


async def read_smart(device_path: str) -> dict[str, Any]:
    if device_path.startswith("/dev/nvme"):
        nvme = await nvme_smart(device_path)
        smart = await smartctl_all(device_path)
        return {"nvme_smart_log": nvme, "smartctl": smart}
    return {"smartctl": await smartctl_all(device_path)}


async def nvme_list() -> dict[str, Any]:
    if not shutil.which("nvme"):
        return {"Devices": []}
    rc, out, _ = await _run("nvme", "list", "-o", "json")
    if rc != 0:
        return {"Devices": []}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"Devices": []}


async def lsblk_json() -> dict[str, Any]:
    rc, out, _ = await _run(
        "lsblk",
        "-J",
        "-b",
        "-o",
        "NAME,KNAME,PATH,TYPE,SIZE,ROTA,TRAN,MODEL,SERIAL,WWN,FSTYPE,MOUNTPOINT,MOUNTPOINTS,LOG-SEC,PHY-SEC",
    )
    if rc != 0:
        return {"blockdevices": []}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"blockdevices": []}
