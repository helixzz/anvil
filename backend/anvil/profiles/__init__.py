from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PhaseSpec:
    name: str
    pattern: str
    block_size: int
    iodepth: int
    numjobs: int
    runtime_s: int
    rwmix_write_pct: int = 0
    ramp_time_s: int = 2
    offset_bytes: int = 0
    size_bytes: int | None = None
    read_only: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pattern": self.pattern,
            "block_size": self.block_size,
            "iodepth": self.iodepth,
            "numjobs": self.numjobs,
            "runtime_s": self.runtime_s,
            "rwmix_write_pct": self.rwmix_write_pct,
            "ramp_time_s": self.ramp_time_s,
            "offset_bytes": self.offset_bytes,
            "size_bytes": self.size_bytes,
            "read_only": self.read_only,
        }


@dataclass(frozen=True)
class Profile:
    name: str
    title: str
    description: str
    destructive: bool
    phases: tuple[PhaseSpec, ...] = field(default_factory=tuple)

    def estimated_duration_seconds(self) -> int:
        return sum(p.runtime_s + p.ramp_time_s for p in self.phases) + 10

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "destructive": self.destructive,
            "phases": [p.as_dict() for p in self.phases],
            "estimated_duration_seconds": self.estimated_duration_seconds(),
        }


QUICK_PROFILE = Profile(
    name="quick",
    title="Quick",
    description=(
        "A fast read-only sanity check equivalent to a small subset of CrystalDiskMark. "
        "Touches only the first 4 GiB of the device and is non-destructive."
    ),
    destructive=False,
    phases=(
        PhaseSpec(
            name="seq_1m_q8t1_read",
            pattern="read",
            block_size=1 << 20,
            iodepth=8,
            numjobs=1,
            runtime_s=20,
            ramp_time_s=2,
            offset_bytes=0,
            size_bytes=4 << 30,
            read_only=True,
        ),
        PhaseSpec(
            name="rnd_4k_q32t1_read",
            pattern="randread",
            block_size=4096,
            iodepth=32,
            numjobs=1,
            runtime_s=20,
            ramp_time_s=2,
            offset_bytes=0,
            size_bytes=4 << 30,
            read_only=True,
        ),
    ),
)


PROFILES: dict[str, Profile] = {
    QUICK_PROFILE.name: QUICK_PROFILE,
}


def get_profile(name: str) -> Profile | None:
    return PROFILES.get(name)


def list_profiles() -> list[Profile]:
    return list(PROFILES.values())
