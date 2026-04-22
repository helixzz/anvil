from __future__ import annotations

import hashlib

from anvil.discovery import DiscoveredDevice


def _make(model: str = "ACME SSD", serial: str = "SN-1234", wwid: str | None = None) -> DiscoveredDevice:
    return DiscoveredDevice(
        path="/dev/nvme0n1",
        kname="nvme0n1",
        model=model,
        serial=serial,
        firmware=None,
        wwid=wwid,
        size_bytes=1 << 40,
        protocol="nvme",
        rotational=False,
        sector_size_logical=512,
        sector_size_physical=512,
        raw_lsblk={},
        raw_nvme=None,
        is_testable=True,
        exclusion_reason=None,
    )


def test_fingerprint_prefers_wwid() -> None:
    wwid = "nvme.1234-abc"
    d = _make(wwid=wwid)
    assert d.fingerprint == hashlib.sha256(wwid.encode()).hexdigest()


def test_fingerprint_falls_back_to_model_serial() -> None:
    d = _make(model="MODEL", serial="SN")
    assert d.fingerprint == hashlib.sha256(b"MODEL|SN").hexdigest()


def test_fingerprint_is_stable_across_instances() -> None:
    a = _make(wwid="x")
    b = _make(wwid="x")
    assert a.fingerprint == b.fingerprint
