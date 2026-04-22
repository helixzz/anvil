"""SNIA SSS PTS v2.0.2 steady-state convergence math.

Per SNIA PTS §7.2 the IOPS test collects a measurement metric (canonically
4 KiB random-write IOPS) over a sliding 5-round window. Steady state is
declared when, simultaneously over the last 5 measurements:

  1. range    : max(x) - min(x)             <= 20% * mean(x)
  2. slope    : |linear_fit_slope| * span   <= 10% * mean(x)

These thresholds are deliberately loose: real SSDs don't flat-line, they
drift. The combination of a bounded range AND a bounded drift prevents
false-positives where, for example, the metric happens to oscillate
inside a 20% band while secularly trending downward.

This module contains only the numerics. It is called by the orchestrator
and by the /snia-analysis API endpoint; no I/O happens here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoundObservation:
    round_idx: int
    metric: float


@dataclass(frozen=True)
class SteadyStateResult:
    steady: bool
    rounds_observed: int
    window: list[float]
    window_mean: float | None
    window_range: float | None
    range_limit: float | None
    range_ok: bool
    slope_per_round: float | None
    slope_across_window: float | None
    slope_limit: float | None
    slope_ok: bool
    reason: str


def evaluate_steady_state(
    observations: list[RoundObservation],
    *,
    window: int = 5,
    range_tolerance: float = 0.20,
    slope_tolerance: float = 0.10,
    min_rounds: int = 5,
) -> SteadyStateResult:
    """Apply the SNIA PTS v2.0.2 steady-state criteria to the last `window` rounds.

    Args:
        observations: ordered list of (round_idx, metric). Typically metric
            is 4 KiB random-write IOPS per SNIA §7.2; the tracker is
            metric-agnostic though.
        window: size of the sliding measurement window (SNIA default 5).
        range_tolerance: maximum (max-min) expressed as a fraction of mean.
        slope_tolerance: maximum |slope| * (x_span) expressed as a fraction
            of mean. Using total drift across the window (rather than
            per-round slope) makes the tolerance dimensionless and
            window-size agnostic.
        min_rounds: observations shorter than this cannot declare steady
            state; they're classified as "warming_up".
    """
    if len(observations) < min_rounds:
        return SteadyStateResult(
            steady=False,
            rounds_observed=len(observations),
            window=[o.metric for o in observations],
            window_mean=None,
            window_range=None,
            range_limit=None,
            range_ok=False,
            slope_per_round=None,
            slope_across_window=None,
            slope_limit=None,
            slope_ok=False,
            reason="warming_up",
        )

    tail = observations[-window:]
    ys = [o.metric for o in tail]
    xs = [o.round_idx for o in tail]
    n = len(ys)
    mean = sum(ys) / n

    if mean == 0:
        return SteadyStateResult(
            steady=False,
            rounds_observed=len(observations),
            window=ys,
            window_mean=0.0,
            window_range=max(ys) - min(ys),
            range_limit=0.0,
            range_ok=False,
            slope_per_round=0.0,
            slope_across_window=0.0,
            slope_limit=0.0,
            slope_ok=False,
            reason="degenerate_mean_zero",
        )

    rng = max(ys) - min(ys)
    range_limit = range_tolerance * mean
    range_ok = rng <= range_limit

    x_mean = sum(xs) / n
    num = sum((xs[i] - x_mean) * (ys[i] - mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    span = xs[-1] - xs[0] if xs[-1] != xs[0] else 1.0
    slope_across = abs(slope) * span
    slope_limit = slope_tolerance * mean
    slope_ok = slope_across <= slope_limit

    steady = range_ok and slope_ok
    reason = (
        "steady"
        if steady
        else ("range_exceeded" if not range_ok else "slope_exceeded")
    )
    return SteadyStateResult(
        steady=steady,
        rounds_observed=len(observations),
        window=ys,
        window_mean=mean,
        window_range=rng,
        range_limit=range_limit,
        range_ok=range_ok,
        slope_per_round=slope,
        slope_across_window=slope_across,
        slope_limit=slope_limit,
        slope_ok=slope_ok,
        reason=reason,
    )
