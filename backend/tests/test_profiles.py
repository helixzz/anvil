from __future__ import annotations

from anvil.profiles import QUICK_PROFILE, get_profile, list_profiles


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


def test_profile_estimated_duration() -> None:
    seconds = QUICK_PROFILE.estimated_duration_seconds()
    assert 30 <= seconds <= 300
