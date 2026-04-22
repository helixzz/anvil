from __future__ import annotations

from anvil.reports import _redact_serial
from anvil.shares import generate_slug


def test_slug_is_url_safe_and_has_entropy() -> None:
    s = generate_slug()
    assert 20 <= len(s) <= 30
    assert all(c.isalnum() or c in "-_" for c in s)


def test_slug_uniqueness_over_many() -> None:
    slugs = {generate_slug() for _ in range(2000)}
    assert len(slugs) == 2000


def test_redact_serial_masks_all_but_last_four() -> None:
    assert _redact_serial("BTHC123456789X") == "••••••••••789X"


def test_redact_serial_short_input() -> None:
    assert _redact_serial("AB12") == "••••"


def test_redact_serial_none() -> None:
    assert _redact_serial(None) == "—"
    assert _redact_serial("") == "—"


def test_redact_in_rendered_html_masks_serial() -> None:
    from anvil.reports import render_run_html

    run = {
        "id": "01TEST",
        "profile_name": "p",
        "status": "complete",
        "started_at": "x",
        "finished_at": "y",
    }
    device = {
        "model": "Samsung PM9A3",
        "serial": "S7KXNE0W500123",
        "firmware": "GDC5402Q",
        "vendor": "Samsung",
        "protocol": "nvme",
        "capacity_bytes": 960197124096,
    }
    html_public = render_run_html(
        run=run, phases=[], timeseries=[], device=device, redact=True
    )
    html_private = render_run_html(
        run=run, phases=[], timeseries=[], device=device, redact=False
    )
    assert "S7KXNE0W500123" not in html_public
    assert "0123" in html_public
    assert "S7KXNE0W500123" in html_private
