from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from anvil.config import get_settings
from anvil.logging import get_logger
from anvil.runner import get_runner_client

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
    mount_points: list[str] = field(default_factory=list)

    @property
    def fingerprint(self) -> str:
        material = self.wwid or f"{self.model}|{self.serial}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveredDevice:
        return cls(
            path=data["path"],
            kname=data["kname"],
            model=data["model"],
            serial=data["serial"],
            firmware=data.get("firmware"),
            wwid=data.get("wwid"),
            size_bytes=int(data.get("size_bytes") or 0),
            protocol=data.get("protocol") or "unknown",
            rotational=bool(data.get("rotational")),
            sector_size_logical=data.get("sector_size_logical"),
            sector_size_physical=data.get("sector_size_physical"),
            raw_lsblk=data.get("raw_lsblk") or {},
            raw_nvme=data.get("raw_nvme"),
            is_testable=bool(data.get("is_testable")),
            exclusion_reason=data.get("exclusion_reason"),
            partitions=list(data.get("partitions") or []),
            mount_points=list(data.get("mount_points") or []),
        )


async def discover() -> list[DiscoveredDevice]:
    """Ask the privileged runner to enumerate and classify block devices.

    Discovery MUST run in the runner because it requires the host's `/proc`,
    `/sys`, and PID namespace to correctly detect which devices back the root
    filesystem, swap, or stacked storage. Running it from inside the API
    container would see only the container's empty mount namespace and falsely
    mark the host's system disk as testable.
    """
    settings = get_settings()
    client = get_runner_client(settings.runner_socket)
    result = await client.discover()
    devices_data = result.get("devices") or []
    return [DiscoveredDevice.from_dict(d) for d in devices_data]
