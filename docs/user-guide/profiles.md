# Profiles

A **profile** is a declarative recipe for a benchmark run. It defines
an ordered sequence of fio phases, each with a block size, I/O depth,
job count, pattern, and runtime. The same profile always produces the
same schedule, which is the whole point: reproducible results across
drives, firmware revisions, and operator shifts.

## Shipped profiles

| Profile | Duration | Purpose |
|---|---|---|
| `sweep_quick` | ~5 min | Block-size smoke test |
| `sweep_full` | ~45 min | Full block-size × iodepth sweep |
| `snia_quick_pts` | ~25 min | SNIA SSS-PTS v2.0.2 Quick IOPS |
| `endurance_soak` | ~2 hours | Sustained write; thermal abort at 75 °C ×6 |

## Phase types

Every phase falls into one of:

- **Precondition** — fills the drive to steady state (sequential
  write, then random write for 2× drive capacity on SNIA profiles).
  Does not contribute to measurement.
- **Measurement** — what you care about. fio json+ output is
  parsed and persisted per-phase and per-sample.
- **Cleanup** — blkdiscard / trim, run after the measurement phases
  finish.

## SNIA steady-state gating

`snia_quick_pts` (and any future SNIA-aware profile) runs 5 rounds of
each block-size / iodepth measurement cell and evaluates steady-state
per [SNIA SSS-PTS v2.0.2](https://www.snia.org/sites/default/files/SSSI/SSS_PTS_2.0.2.pdf):

1. Compute the arithmetic mean of the last 5 rounds (the "measurement
   window").
2. Fit a linear slope across the 5 rounds.
3. **Range gate**: the maximum absolute excursion from the window
   mean must be ≤ 20 % of the mean.
4. **Slope gate**: the slope across the window must be ≤ 10 % of the
   mean per round.

Runs that reach steady-state show a SniaAnalysisCard on the Run
Detail page with the computed window mean, range, slope, and
pass/fail per gate. Runs that don't converge within 25 rounds still
publish their last round's numbers; the card marks them
`slope_ok=false` or `range_ok=false` so you can tell the difference
between a clean plateau and a drifting drive.

## Authoring your own profile

Profiles are Python modules under `backend/anvil/profiles/`. Each
module defines a top-level `profile: Profile` with a name, description,
and phases. After adding a module, import it in
`backend/anvil/profiles/__init__.py` and bump the backend version.

See [DESIGN.md](../DESIGN.md) for the full profile schema.
