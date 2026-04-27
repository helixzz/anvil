from __future__ import annotations

import sys
from pathlib import Path

RUNNER_ROOT = Path(__file__).resolve().parents[2] / "runner"
if str(RUNNER_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNNER_ROOT))

from anvil_runner.fio import (  # noqa: E402
    _nested_float,
    _parse_last_json_object,
    _safe_float,
    _safe_int,
    _snapshot_to_sample,
    _summarise,
)

# ---- _safe_float / _safe_int -------------------------------------------------

def test_safe_float_accepts_numbers() -> None:
    assert _safe_float(3.14) == 3.14
    assert _safe_float(42) == 42.0


def test_safe_float_accepts_strings() -> None:
    assert _safe_float("3.14") == 3.14
    assert _safe_float("42") == 42.0


def test_safe_float_rejects_invalid() -> None:
    assert _safe_float("abc") is None
    assert _safe_float(None) is None


def test_safe_int_returns_int() -> None:
    assert _safe_int(42) == 42
    assert _safe_int("42") == 42
    assert _safe_int(3.9) == 3


# ---- _nested_float -----------------------------------------------------------

def test_nested_float_retrieves_deeply_nested_value() -> None:
    section = {
        "a": {"b": {"c": "123.45"}},
    }
    assert _nested_float(section, "a", "b", "c") == 123.45


def test_nested_float_returns_none_when_key_missing() -> None:
    section = {"a": {}}
    assert _nested_float(section, "a", "x") is None


# ---- _summarise --------------------------------------------------------------

def test_summarise_produces_read_write_metrics() -> None:
    fio = {
        "jobs": [
            {
                "read": {
                    "iops": 100_000,
                    "bw_bytes": 400_000_000,
                    "lat_ns": {"mean": 1_200.0},
                    "clat_ns": {"mean": 1_200.0, "percentile": {"99.000000": 3_500.0, "99.990000": 12_000.0}},
                },
                "write": {
                    "iops": 50_000,
                    "bw_bytes": 200_000_000,
                    "lat_ns": {"mean": 800.0},
                    "clat_ns": {"mean": 800.0, "percentile": {"99.000000": 2_000.0, "99.990000": 8_000.0}},
                },
            }
        ]
    }
    s = _summarise(fio)
    assert s["read_iops"] == 100_000.0
    assert s["read_bw_bytes"] == 400_000_000.0
    assert s["read_clat_mean_ns"] == 1_200.0
    assert s["read_clat_p99_ns"] == 3_500.0
    assert s["read_clat_p9999_ns"] == 12_000.0
    assert s["write_iops"] == 50_000.0
    assert s["write_bw_bytes"] == 200_000_000.0
    assert s["write_clat_mean_ns"] == 800.0
    assert s["write_clat_p99_ns"] == 2_000.0


def test_summarise_missing_write_job() -> None:
    fio = {
        "jobs": [
            {
                "read": {"iops": 10, "bw_bytes": 40, "lat_ns": {"mean": 100}, "clat_ns": {"percentile": {}}},
            }
        ]
    }
    s = _summarise(fio)
    assert s["read_iops"] == 10.0
    assert s["write_iops"] is None


# ---- _snapshot_to_sample -----------------------------------------------------

def test_snapshot_to_sample_extracts_phase_metrics() -> None:
    snap = {
        "global_options": {},
        "jobs": [
            {
                "read": {
                    "iops": 220_000,
                    "bw_bytes": 880_000_000,
                    "lat_ns": {"mean": 950.0},
                    "clat_ns": {"percentile": {}},
                },
                "write": {
                    "iops": 110_000,
                    "bw_bytes": 440_000_000,
                    "lat_ns": {"mean": 450.0},
                    "clat_ns": {"percentile": {}},
                },
            }
        ],
    }
    sample = _snapshot_to_sample("rnd_4k_q32t1_read", snap)
    assert sample is not None
    assert sample["phase_name"] == "rnd_4k_q32t1_read"
    assert sample["read_iops"] == 220_000.0
    assert sample["write_iops"] == 110_000.0
    assert sample["read_bw_bytes"] == 880_000_000.0


# ---- _parse_last_json_object ------------------------------------------------

def test_parse_last_json_finds_complete_object() -> None:
    text = 'some log\n{"a":1}\n{"b":2}\nmore log'
    result = _parse_last_json_object(text)
    assert result == {"b": 2}


def test_parse_last_json_returns_none_for_no_json() -> None:
    assert _parse_last_json_object("just text") is None


def test_parse_last_json_handles_empty_input() -> None:
    assert _parse_last_json_object("") is None
