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


def test_fingerprint_uses_model_and_serial() -> None:
    d = _make(model="MODEL", serial="SN")
    assert d.fingerprint == hashlib.sha256(b"MODEL|SN").hexdigest()


def test_fingerprint_ignores_wwid() -> None:
    with_wwid = _make(model="MODEL", serial="SN", wwid="nvme.abc")
    without_wwid = _make(model="MODEL", serial="SN", wwid=None)
    assert with_wwid.fingerprint == without_wwid.fingerprint


def test_fingerprint_is_stable_across_instances() -> None:
    a = _make()
    b = _make()
    assert a.fingerprint == b.fingerprint
