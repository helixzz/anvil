from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KIB = 1024
MIB = 1024 * 1024
GIB = 1024 * 1024 * 1024


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


def _read_phase(
    name: str,
    *,
    pattern: str,
    block_size: int,
    iodepth: int,
    numjobs: int = 1,
    runtime_s: int = 20,
    size_bytes: int = 4 * GIB,
) -> PhaseSpec:
    return PhaseSpec(
        name=name,
        pattern=pattern,
        block_size=block_size,
        iodepth=iodepth,
        numjobs=numjobs,
        runtime_s=runtime_s,
        ramp_time_s=2,
        offset_bytes=0,
        size_bytes=size_bytes,
        read_only=True,
    )


def _mixed_phase(
    name: str,
    *,
    pattern: str,
    block_size: int,
    iodepth: int,
    rwmix_write_pct: int,
    numjobs: int = 1,
    runtime_s: int = 30,
    size_bytes: int | None = None,
) -> PhaseSpec:
    return PhaseSpec(
        name=name,
        pattern=pattern,
        block_size=block_size,
        iodepth=iodepth,
        numjobs=numjobs,
        runtime_s=runtime_s,
        ramp_time_s=3,
        offset_bytes=0,
        size_bytes=size_bytes,
        rwmix_write_pct=rwmix_write_pct,
        read_only=False,
    )


QUICK_PROFILE = Profile(
    name="quick",
    title="Quick",
    description=(
        "Fast read-only sanity check: sequential 1 MiB QD8 + random 4 KiB QD32 "
        "reads on the first 4 GiB. Non-destructive, ~1 minute."
    ),
    destructive=False,
    phases=(
        _read_phase("seq_1m_q8t1_read", pattern="read", block_size=MIB, iodepth=8),
        _read_phase("rnd_4k_q32t1_read", pattern="randread", block_size=4 * KIB, iodepth=32),
    ),
)


STANDARD_READ_PROFILE = Profile(
    name="standard_read",
    title="Standard (read-only)",
    description=(
        "Non-destructive read-coverage sweep: sequential 1 MiB at QD 1/8/32 and 128 KiB, "
        "plus random 4 KiB read QD sweep 1/4/16/32/64/128. Touches the first 16 GiB. "
        "~6 minutes."
    ),
    destructive=False,
    phases=(
        _read_phase("seq_1m_q1t1_read", pattern="read", block_size=MIB, iodepth=1, runtime_s=20, size_bytes=16 * GIB),
        _read_phase("seq_1m_q8t1_read", pattern="read", block_size=MIB, iodepth=8, runtime_s=20, size_bytes=16 * GIB),
        _read_phase("seq_1m_q32t1_read", pattern="read", block_size=MIB, iodepth=32, runtime_s=20, size_bytes=16 * GIB),
        _read_phase("seq_128k_q32t1_read", pattern="read", block_size=128 * KIB, iodepth=32, runtime_s=20, size_bytes=16 * GIB),
        _read_phase("rnd_4k_q1t1_read", pattern="randread", block_size=4 * KIB, iodepth=1, runtime_s=30, size_bytes=16 * GIB),
        _read_phase("rnd_4k_q4t1_read", pattern="randread", block_size=4 * KIB, iodepth=4, runtime_s=30, size_bytes=16 * GIB),
        _read_phase("rnd_4k_q16t1_read", pattern="randread", block_size=4 * KIB, iodepth=16, runtime_s=30, size_bytes=16 * GIB),
        _read_phase("rnd_4k_q32t1_read", pattern="randread", block_size=4 * KIB, iodepth=32, runtime_s=30, size_bytes=16 * GIB),
        _read_phase("rnd_4k_q64t1_read", pattern="randread", block_size=4 * KIB, iodepth=64, runtime_s=30, size_bytes=16 * GIB),
        _read_phase("rnd_4k_q128t1_read", pattern="randread", block_size=4 * KIB, iodepth=128, runtime_s=30, size_bytes=16 * GIB),
        _read_phase("rnd_8k_q32t1_read", pattern="randread", block_size=8 * KIB, iodepth=32, runtime_s=30, size_bytes=16 * GIB),
    ),
)


STANDARD_PROFILE = Profile(
    name="standard",
    title="Standard (destructive)",
    description=(
        "ezFIO-style sweep: sequential block-size sweep, random 4 KiB QD sweep, "
        "and a short mixed-workload stability test. Writes to the drive — all data "
        "on the selected device will be destroyed. ~15 minutes."
    ),
    destructive=True,
    phases=(
        _mixed_phase("seq_128k_q32t1_write_precond", pattern="write", block_size=128 * KIB, iodepth=32, rwmix_write_pct=100, runtime_s=30),
        _mixed_phase("seq_1m_q8t1_read", pattern="read", block_size=MIB, iodepth=8, rwmix_write_pct=0, runtime_s=20),
        _mixed_phase("seq_1m_q8t1_write", pattern="write", block_size=MIB, iodepth=8, rwmix_write_pct=100, runtime_s=20),
        _mixed_phase("rnd_4k_q1t1_read", pattern="randread", block_size=4 * KIB, iodepth=1, rwmix_write_pct=0, runtime_s=30),
        _mixed_phase("rnd_4k_q32t1_read", pattern="randread", block_size=4 * KIB, iodepth=32, rwmix_write_pct=0, runtime_s=30),
        _mixed_phase("rnd_4k_q128t1_read", pattern="randread", block_size=4 * KIB, iodepth=128, rwmix_write_pct=0, runtime_s=30),
        _mixed_phase("rnd_4k_q1t1_write", pattern="randwrite", block_size=4 * KIB, iodepth=1, rwmix_write_pct=100, runtime_s=30),
        _mixed_phase("rnd_4k_q32t1_write", pattern="randwrite", block_size=4 * KIB, iodepth=32, rwmix_write_pct=100, runtime_s=30),
        _mixed_phase("rnd_4k_q128t1_write", pattern="randwrite", block_size=4 * KIB, iodepth=128, rwmix_write_pct=100, runtime_s=30),
        _mixed_phase("rnd_4k_q32t1_mix70r30w", pattern="randrw", block_size=4 * KIB, iodepth=32, rwmix_write_pct=30, runtime_s=60),
        _mixed_phase("rnd_4k_q128t1_mix70r30w_stability", pattern="randrw", block_size=4 * KIB, iodepth=128, rwmix_write_pct=30, runtime_s=300),
    ),
)


MYSQL_OLTP_PROFILE = Profile(
    name="mysql_oltp",
    title="MySQL OLTP (8K 65/35)",
    description=(
        "Simulates an OLTP database workload per SNIA guidance: random 8 KiB with a "
        "65% read / 35% write mix at QD 32 across 4 jobs, preceded by a short "
        "preconditioning pass. Destructive. ~5 minutes."
    ),
    destructive=True,
    phases=(
        _mixed_phase("precondition_rnd_4k_q256", pattern="randwrite", block_size=4 * KIB, iodepth=256, rwmix_write_pct=100, runtime_s=60),
        _mixed_phase("oltp_rnd_8k_65r_35w", pattern="randrw", block_size=8 * KIB, iodepth=32, numjobs=4, rwmix_write_pct=35, runtime_s=180),
    ),
)


OLAP_SCAN_PROFILE = Profile(
    name="olap_scan",
    title="OLAP scan (1M read)",
    description=(
        "Simulates a data-warehouse scan: sustained 1 MiB sequential reads at QD 64 "
        "across 4 jobs. Non-destructive. ~3 minutes."
    ),
    destructive=False,
    phases=(
        _read_phase("olap_seq_1m_q64t4_read", pattern="read", block_size=MIB, iodepth=64, numjobs=4, runtime_s=120, size_bytes=32 * GIB),
    ),
)


VIDEO_EDITING_PROFILE = Profile(
    name="video_editing",
    title="Video editing (1M 50/50)",
    description=(
        "Simulates NLE scrubbing and render-out: sustained 1 MiB 50/50 read/write "
        "at QD 32 across 2 jobs. Destructive. ~3 minutes."
    ),
    destructive=True,
    phases=(
        _mixed_phase("video_seq_1m_q32t2_50r50w", pattern="rw", block_size=MIB, iodepth=32, numjobs=2, rwmix_write_pct=50, runtime_s=180),
    ),
)


DESKTOP_GENERAL_PROFILE = Profile(
    name="desktop_general",
    title="Desktop general (4K QD4 60/40)",
    description=(
        "Approximates bursty desktop I/O: random 4 KiB 60% read / 40% write at QD 4, "
        "single job. Destructive. ~2 minutes."
    ),
    destructive=True,
    phases=(
        _mixed_phase("desk_rnd_4k_q4t1_60r40w", pattern="randrw", block_size=4 * KIB, iodepth=4, rwmix_write_pct=40, runtime_s=120),
    ),
)


STABILITY_PROFILE = Profile(
    name="stability",
    title="Stability (20 min, 4K 70/30)",
    description=(
        "ezFIO-style sustained stability test: 20 minutes of random 4 KiB 70% read / "
        "30% write at QD 32 with 8 jobs. Exposes QoS (latency variance) and thermal "
        "throttling. Destructive. ~20 minutes."
    ),
    destructive=True,
    phases=(
        _mixed_phase("precondition_rnd_4k_q256", pattern="randwrite", block_size=4 * KIB, iodepth=256, rwmix_write_pct=100, runtime_s=60),
        _mixed_phase("stability_rnd_4k_q32t8_70r30w", pattern="randrw", block_size=4 * KIB, iodepth=32, numjobs=8, rwmix_write_pct=30, runtime_s=1200),
    ),
)


SNIA_PTS_BLOCK_SIZES = (4 * KIB, 64 * KIB, 1 * MIB)
SNIA_PTS_RW_MIXES = (0, 35, 100)
SNIA_PTS_ROUND_COUNT = 5
SNIA_PTS_PRECOND_SECONDS = 60
SNIA_PTS_CELL_SECONDS = 45


def _snia_quick_phases() -> tuple[PhaseSpec, ...]:
    """Generate a SNIA-flavoured test matrix: 5 rounds x (3 BS x 3 R/W mixes).

    Each cell runs for 45 s at QD32 with 2 jobs so the round completes in
    3*3*45 = 405 s ~= 7 min; 5 rounds = 35 min plus a 60 s workload-
    independent seq-write preconditioning pass. The runner writes the
    entire addressable test region for preconditioning before any cell.

    Phase naming: snia_r<round>_bs<bs>_w<rwmix_write_pct>_rw so the post-
    run analysis endpoint can regex-group them by round.
    """
    phases: list[PhaseSpec] = [
        _mixed_phase(
            "snia_precondition_seq_1m",
            pattern="write",
            block_size=1 * MIB,
            iodepth=32,
            rwmix_write_pct=100,
            runtime_s=SNIA_PTS_PRECOND_SECONDS,
        ),
    ]
    for r in range(1, SNIA_PTS_ROUND_COUNT + 1):
        for bs in SNIA_PTS_BLOCK_SIZES:
            for rw_read_pct in (100, 65, 0):
                rwmix_write_pct = 100 - rw_read_pct
                if rwmix_write_pct == 0:
                    pattern = "randread"
                elif rwmix_write_pct == 100:
                    pattern = "randwrite"
                else:
                    pattern = "randrw"
                bs_label = "4k" if bs == 4 * KIB else "64k" if bs == 64 * KIB else "1m"
                phases.append(
                    _mixed_phase(
                        f"snia_r{r}_bs{bs_label}_w{rwmix_write_pct}",
                        pattern=pattern,
                        block_size=bs,
                        iodepth=32,
                        numjobs=2,
                        rwmix_write_pct=rwmix_write_pct,
                        runtime_s=SNIA_PTS_CELL_SECONDS,
                    )
                )
    return tuple(phases)


SNIA_QUICK_PTS_PROFILE = Profile(
    name="snia_quick_pts",
    title="SNIA PTS Quick (5 rounds × 3×3 matrix)",
    description=(
        "Streamlined SNIA PTS IOPS test: workload-independent 128K seq write "
        "preconditioning, then 5 rounds of a 3×3 matrix (block sizes 4 KiB / "
        "64 KiB / 1 MiB at R/W mixes 100/0, 65/35, 0/100) at QD 32 with 2 jobs. "
        "Steady-state convergence is checked after the run using the 4K 100% "
        "write IOPS metric per SNIA §7.2 (range ≤ 20 %, slope drift ≤ 10 %). "
        "Destructive. ~35 minutes total."
    ),
    destructive=True,
    phases=_snia_quick_phases(),
)


ENDURANCE_SOAK_PROFILE = Profile(
    name="endurance_soak",
    title="Endurance soak (2 h sustained 4 K random write)",
    description=(
        "Long sustained random-write endurance probe: 2 hours at 4 KiB QD 32 "
        "with 8 jobs to exercise the drive under prolonged heavy write. SMART "
        "temperature is polled every 5 s during the run (same as every other "
        "profile); the runner aborts with a thermal-throttle reason if the "
        "drive sustains ≥ 75 °C for 6 consecutive samples (≈ 30 s). "
        "Destructive, ~2 hours."
    ),
    destructive=True,
    phases=(
        _mixed_phase(
            "endurance_precondition_seq_1m",
            pattern="write",
            block_size=1 * MIB,
            iodepth=32,
            rwmix_write_pct=100,
            runtime_s=60,
        ),
        _mixed_phase(
            "endurance_soak_rnd_4k_q32t8",
            pattern="randwrite",
            block_size=4 * KIB,
            iodepth=32,
            numjobs=8,
            rwmix_write_pct=100,
            runtime_s=7200,
        ),
    ),
)


def _help_phase(
    name: str, pattern: str, bs: int, qd: int, nj: int = 1,
    rwmix: int = 0, runtime_s: int = 60, ro: bool = False,
) -> PhaseSpec:
    return PhaseSpec(
        name=name, pattern=pattern, block_size=bs, iodepth=qd, numjobs=nj,
        runtime_s=runtime_s, rwmix_write_pct=rwmix, ramp_time_s=2,
        read_only=ro,
    )


def _rw_phase(
    name: str, pattern: str, bs: int, qd: int, nj: int = 1,
    rwmix: int = 0, runtime_s: int = 60,
) -> PhaseSpec:
    """A destructive-safe phase: uses _mixed_phase semantics but allows
    rwmix_write_pct=0 for pure-read phases inside destructive profiles.
    """
    return _mixed_phase(name, pattern=pattern, block_size=bs, iodepth=qd,
                        numjobs=nj, rwmix_write_pct=rwmix, runtime_s=runtime_s)


# ── StorageReview Four Corners ──────────────────────────────────────────────

def _sr_four_corners_phases() -> tuple[PhaseSpec, ...]:
    precondition = _help_phase(
        name="sr_precond_seq_128k", pattern="write",
        bs=128 * KIB, qd=32, rwmix=100, runtime_s=60,
    )
    return (
        precondition,
        _rw_phase("sr_4k_rand_read_128t", pattern="randread", bs=4 * KIB, qd=1, nj=128, runtime_s=120),
        _help_phase("sr_4k_rand_write_64t", pattern="randwrite", bs=4 * KIB, qd=1, nj=64, rwmix=100, runtime_s=120),
        _rw_phase("sr_64k_seq_read_16t", pattern="read", bs=64 * KIB, qd=1, nj=16, runtime_s=120),
        _help_phase("sr_64k_seq_write_8t", pattern="write", bs=64 * KIB, qd=1, nj=8, rwmix=100, runtime_s=120),
    )


SR_FOUR_CORNERS_PROFILE = Profile(
    name="sr_four_corners",
    title="SR Four Corners (4K/64K R/W)",
    description=(
        "StorageReview-style four-corner benchmark: 4 KiB random read (128 threads) "
        "+ write (64T), 64 KiB sequential read (16T) + write (8T). Each cell "
        "runs for 2 minutes; preconditioning pass of 128 KiB sequential write "
        "beforehand. Destructive, ~10 minutes."
    ),
    destructive=True,
    phases=_sr_four_corners_phases(),
)


# ── StorageReview Deep Latency Sweep ────────────────────────────────────────

def _sr_deep_sweep_phases() -> tuple[PhaseSpec, ...]:
    qd_sweep = (1, 2, 4, 8, 16, 32)
    nj_sweep = (1, 2, 4, 8)
    phases: list[PhaseSpec] = [
        _help_phase("sr_deep_precond_seq_1m", pattern="write", bs=1 * MIB, qd=4, nj=4, rwmix=100, runtime_s=120),
    ]
    for block, label in ((4 * KIB, "4k"), (16 * KIB, "16k"), (64 * KIB, "64k"), (128 * KIB, "128k")):
        phases.append(_help_phase(
            f"sr_deep_precond_{label}", pattern="write",
            bs=block, qd=32, rwmix=100, runtime_s=30,
        ))
        for nj in nj_sweep:
            for qd in qd_sweep:
                read_name = f"sr_deep_{label}_read_qd{qd}t{nj}"
                write_name = f"sr_deep_{label}_write_qd{qd}t{nj}"
                phases.append(_rw_phase(read_name, pattern="randread", bs=block, qd=qd, nj=nj, runtime_s=30))
                phases.append(_help_phase(write_name, pattern="randwrite", bs=block, qd=qd, nj=nj, rwmix=100, runtime_s=30))
    return tuple(phases)


SR_DEEP_SWEEP_PROFILE = Profile(
    name="sr_deep_sweep",
    title="SR Deep IODepth×Threads Sweep",
    description=(
        "StorageReview enterprise-style QD×threads sweep across 4 KiB / 16 KiB / "
        "64 KiB / 128 KiB block sizes, with per-block-size preconditioning. Each "
        "cell (random-read and random-write at one QD×NJ point) runs for 30 s; "
        "192 cells total. Designed to produce latency-vs-throughput curves across "
        "the drive's entire performance envelope. Destructive, ~2 hours."
    ),
    destructive=True,
    phases=_sr_deep_sweep_phases(),
)


# ── ezFIO Comprehensive ─────────────────────────────────────────────────────

def _ezfio_comprehensive_phases() -> tuple[PhaseSpec, ...]:
    bslist = (512, 1 * KIB, 2 * KIB, 4 * KIB, 8 * KIB, 16 * KIB, 32 * KIB, 64 * KIB, 128 * KIB)
    tlist = (1, 2, 4, 8, 16, 32, 64, 128, 256)
    phases: list[PhaseSpec] = []

    # Preconditioning: sequential fill + random fill
    phases.append(_help_phase("ezfio_precond_seq_128k_q64", pattern="write", bs=128 * KIB, qd=64, rwmix=100, runtime_s=120))
    phases.append(_help_phase("ezfio_precond_rnd_4k_q256", pattern="randwrite", bs=4 * KIB, qd=256, rwmix=100, runtime_s=120))

    # Group 1: Sequential Read by Block Size
    for bs in bslist:
        label = _bs_label(bs)
        phases.append(_rw_phase(f"ezfio_g1_seq_read_{label}_q256", pattern="read", bs=bs, qd=256, nj=1, runtime_s=60))

    # Group 2: Random Read by Block Size (16t)
    for bs in bslist:
        label = _bs_label(bs)
        phases.append(_rw_phase(f"ezfio_g2_rnd_read_{label}_q16t16", pattern="randread", bs=bs, qd=16, nj=16, runtime_s=60))

    # Group 3: Sequential Write QD1 by Block Size
    for bs in bslist:
        label = _bs_label(bs)
        phases.append(_help_phase(f"ezfio_g3_seq_write_{label}_q1", pattern="write", bs=bs, qd=1, nj=1, rwmix=100, runtime_s=60))

    # Group 4: 4K Random Read by Thread Count
    for t in tlist:
        phases.append(_rw_phase(f"ezfio_g4_rnd_4k_read_q1t{t}", pattern="randread", bs=4 * KIB, qd=1, nj=t, runtime_s=60))

    # Group 5: 4K Random 70/30 by Thread Count
    for t in tlist:
        phases.append(_help_phase(f"ezfio_g5_rnd_4k_70r30w_q1t{t}", pattern="randrw", bs=4 * KIB, qd=1, nj=t, rwmix=30, runtime_s=60))

    # Group 6: 4K Stability 70/30 (20 min, 200t)
    phases.append(_help_phase("ezfio_g6_stability_4k_70r30w_q1t200", pattern="randrw", bs=4 * KIB, qd=1, nj=200, rwmix=30, runtime_s=1200))

    # Group 7: 4K Random Write by Thread Count
    for t in tlist:
        phases.append(_help_phase(f"ezfio_g7_rnd_4k_write_q1t{t}", pattern="randwrite", bs=4 * KIB, qd=1, nj=t, rwmix=100, runtime_s=60))

    # Group 8: Random Write by Block Size (16t)
    for bs in bslist:
        label = _bs_label(bs)
        phases.append(_help_phase(f"ezfio_g8_rnd_write_{label}_q16t16", pattern="randwrite", bs=bs, qd=16, nj=16, rwmix=100, runtime_s=60))

    return tuple(phases)


def _bs_label(bs: int) -> str:
    if bs >= 128 * KIB:
        return "128k"
    if bs >= 64 * KIB:
        return "64k"
    if bs >= 32 * KIB:
        return "32k"
    if bs >= 16 * KIB:
        return "16k"
    if bs >= 8 * KIB:
        return "8k"
    if bs >= 4 * KIB:
        return "4k"
    if bs >= 2 * KIB:
        return "2k"
    if bs >= 1 * KIB:
        return "1k"
    return "512b"


EZFIO_COMPREHENSIVE_PROFILE = Profile(
    name="ezfio_comprehensive",
    title="ezFIO Comprehensive (full shmoo)",
    description=(
        "ezFIO-style systematic benchmark: 8 test groups covering sequential "
        "read/write by block size, random read/write by block size, 4 KiB random "
        "by thread count (read, write, and 70/30 mixed), plus a 20-minute 4 KiB "
        "70/30 stability probe. 90 individual measurement cells plus 2 "
        "preconditioning passes. Designed to match the ezfio.py default run. "
        "Destructive, ~3.5–5 hours depending on drive speed."
    ),
    destructive=True,
    phases=_ezfio_comprehensive_phases(),
)


PROFILES: dict[str, Profile] = {
    p.name: p
    for p in (
        QUICK_PROFILE,
        STANDARD_READ_PROFILE,
        STANDARD_PROFILE,
        MYSQL_OLTP_PROFILE,
        OLAP_SCAN_PROFILE,
        VIDEO_EDITING_PROFILE,
        DESKTOP_GENERAL_PROFILE,
        STABILITY_PROFILE,
        SNIA_QUICK_PTS_PROFILE,
        ENDURANCE_SOAK_PROFILE,
        SR_FOUR_CORNERS_PROFILE,
        SR_DEEP_SWEEP_PROFILE,
        EZFIO_COMPREHENSIVE_PROFILE,
    )
}


def get_profile(name: str) -> Profile | None:
    return PROFILES.get(name)


def list_profiles() -> list[Profile]:
    return list(PROFILES.values())
