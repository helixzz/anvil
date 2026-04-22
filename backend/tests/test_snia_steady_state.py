from __future__ import annotations

import pytest

from anvil.profiles.snia import (
    RoundObservation,
    evaluate_steady_state,
)


def _obs(metrics: list[float]) -> list[RoundObservation]:
    return [RoundObservation(round_idx=i + 1, metric=m) for i, m in enumerate(metrics)]


def test_warming_up_when_below_min_rounds() -> None:
    result = evaluate_steady_state(_obs([100, 110, 120]))
    assert result.steady is False
    assert result.reason == "warming_up"
    assert result.rounds_observed == 3


def test_steady_when_flat() -> None:
    result = evaluate_steady_state(_obs([100, 101, 99, 100, 100]))
    assert result.steady is True
    assert result.reason == "steady"
    assert result.range_ok is True
    assert result.slope_ok is True
    assert result.window_mean == pytest.approx(100.0, rel=0.01)


def test_range_violation() -> None:
    # Range 60, mean ~90 → 60 / 90 = 66% > 20% tolerance
    result = evaluate_steady_state(_obs([60, 120, 60, 120, 60]))
    assert result.steady is False
    assert result.reason == "range_exceeded"
    assert result.range_ok is False


def test_slope_violation_monotonic_increase() -> None:
    # Monotonic rise 100→108, range 8 (~8%, passes range), but slope
    # across 4-round span = 2 per round × 4 = 8 → 8/104 ≈ 7.7% (passes).
    # Push harder: 100→130 keeps range at 30%, which fails first.
    # Construct one that passes range but fails slope: 100, 101, 102,
    # 103, 120 — range 20 / mean ~105 ≈ 19% passes; slope dominated by
    # last jump: regression slope ~4.1/round × 4 = 16.4, mean 105,
    # 16.4/105 ≈ 15.6% > 10%.
    result = evaluate_steady_state(_obs([100, 101, 102, 103, 120]))
    assert result.steady is False
    # range is 20, limit is 20% of mean=105.2 → 21.04, so range passes
    assert result.range_ok is True
    assert result.slope_ok is False
    assert result.reason == "slope_exceeded"


def test_sliding_window_uses_only_last_five() -> None:
    # First five rounds wildly unsteady, last five rounds flat → steady.
    metrics = [10, 1000, 10, 1000, 10,   500, 498, 502, 499, 501]
    result = evaluate_steady_state(_obs(metrics))
    assert result.steady is True
    assert result.window == [500, 498, 502, 499, 501]


def test_degenerate_zero_mean() -> None:
    result = evaluate_steady_state(_obs([0, 0, 0, 0, 0]))
    assert result.steady is False
    assert result.reason == "degenerate_mean_zero"


def test_custom_thresholds_tighter() -> None:
    # Normally flat → steady, but with a 1% tolerance it fails.
    result = evaluate_steady_state(
        _obs([100, 101, 99, 100, 100]),
        range_tolerance=0.01,
        slope_tolerance=0.01,
    )
    assert result.steady is False
    assert result.range_ok is False


def test_full_snia_default_tolerances_documented() -> None:
    # SNIA PTS v2.0.2 defaults: 20% range, 10% slope, 5-round window.
    # Verify the function's published defaults haven't drifted.
    import inspect

    sig = inspect.signature(evaluate_steady_state)
    assert sig.parameters["window"].default == 5
    assert sig.parameters["range_tolerance"].default == 0.20
    assert sig.parameters["slope_tolerance"].default == 0.10
    assert sig.parameters["min_rounds"].default == 5
