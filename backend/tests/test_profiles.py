from __future__ import annotations

import pytest

from anvil.profiles import (
    PROFILES,
    QUICK_PROFILE,
    get_profile,
    list_profiles,
)


def test_quick_profile_is_non_destructive() -> None:
    assert QUICK_PROFILE.destructive is False
    assert all(p.read_only for p in QUICK_PROFILE.phases)


def test_quick_profile_has_seq_and_random_phases() -> None:
    names = {p.name for p in QUICK_PROFILE.phases}
    assert "seq_1m_q8t1_read" in names
    assert "rnd_4k_q32t1_read" in names


def test_profile_lookup() -> None:
    assert get_profile("quick") is QUICK_PROFILE
    assert get_profile("does-not-exist") is None
    assert QUICK_PROFILE in list_profiles()


def test_profile_estimated_duration_quick() -> None:
    seconds = QUICK_PROFILE.estimated_duration_seconds()
    assert 30 <= seconds <= 300


@pytest.mark.parametrize("name", list(PROFILES.keys()))
def test_every_profile_has_sane_shape(name: str) -> None:
    p = PROFILES[name]
    assert p.name == name
    assert p.title
    assert len(p.description) >= 20
    assert p.phases, f"profile {name} has no phases"
    for phase in p.phases:
        assert phase.block_size > 0
        assert phase.iodepth >= 1
        assert phase.numjobs >= 1
        assert phase.runtime_s > 0
        assert 0 <= phase.rwmix_write_pct <= 100
        if p.destructive:
            assert not phase.read_only, (
                f"destructive profile {name} has read_only phase {phase.name}"
            )
        if not p.destructive:
            assert phase.read_only, (
                f"non-destructive profile {name} has non-read-only phase {phase.name}"
            )


@pytest.mark.parametrize(
    "name,expected_destructive",
    [
        ("quick", False),
        ("standard_read", False),
        ("olap_scan", False),
        ("standard", True),
        ("mysql_oltp", True),
        ("video_editing", True),
        ("desktop_general", True),
        ("stability", True),
    ],
)
def test_destructive_flag(name: str, expected_destructive: bool) -> None:
    profile = get_profile(name)
    assert profile is not None
    assert profile.destructive is expected_destructive


def test_profile_phase_names_unique_within_profile() -> None:
    for p in list_profiles():
        names = [ph.name for ph in p.phases]
        assert len(names) == len(set(names)), (
            f"duplicate phase names in {p.name}: {names}"
        )


def test_catalog_contains_expected_profiles() -> None:
    expected = {
        "quick",
        "standard_read",
        "standard",
        "mysql_oltp",
        "olap_scan",
        "video_editing",
        "desktop_general",
        "stability",
    }
    assert expected <= set(PROFILES.keys())


def test_profile_as_dict_roundtrip() -> None:
    d = QUICK_PROFILE.as_dict()
    assert d["name"] == "quick"
    assert d["destructive"] is False
    assert len(d["phases"]) == len(QUICK_PROFILE.phases)
    assert d["estimated_duration_seconds"] == QUICK_PROFILE.estimated_duration_seconds()
