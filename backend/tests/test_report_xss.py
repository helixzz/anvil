from __future__ import annotations

from anvil.reports import render_run_html


def test_profile_name_is_html_escaped() -> None:
    run = {
        "id": "01TEST",
        "profile_name": "<script>alert('xss')</script>",
        "status": "complete",
        "started_at": "-",
        "finished_at": "-",
    }
    out = render_run_html(run=run, phases=[], timeseries=[], device=None)
    assert "<script>alert" not in out
    assert "&lt;script&gt;alert" in out


def test_device_model_is_html_escaped() -> None:
    run = {"id": "R", "profile_name": "p", "status": "complete", "started_at": "-", "finished_at": "-"}
    device = {
        "model": '"><img src=x onerror=alert(1)>',
        "serial": "S",
        "firmware": None,
        "vendor": None,
        "protocol": "nvme",
        "capacity_bytes": 0,
    }
    out = render_run_html(run=run, phases=[], timeseries=[], device=device)
    assert '"><img src=x onerror=alert(1)>' not in out
    assert "&lt;img src=x onerror=alert(1)&gt;" in out
    assert "&quot;&gt;" in out


def test_phase_fields_are_html_escaped() -> None:
    run = {"id": "R", "profile_name": "p", "status": "complete", "started_at": "-", "finished_at": "-"}
    phases = [
        {
            "phase_order": 1,
            "phase_name": "<b>pwn</b>",
            "pattern": "read",
            "block_size": 4096,
            "iodepth": 1,
            "numjobs": 1,
            "read_iops": 1,
            "read_bw_bytes": 1,
            "read_clat_mean_ns": 1,
            "read_clat_p99_ns": 1,
            "write_iops": None,
            "write_bw_bytes": None,
            "write_clat_mean_ns": None,
            "write_clat_p99_ns": None,
        }
    ]
    out = render_run_html(run=run, phases=phases, timeseries=[], device=None)
    assert "<b>pwn</b>" not in out
    assert "&lt;b&gt;pwn&lt;/b&gt;" in out


def test_redact_still_escapes() -> None:
    run = {"id": "R", "profile_name": "p", "status": "complete", "started_at": "-", "finished_at": "-"}
    device = {
        "model": "<svg/onload=alert(1)>Samsung",
        "serial": "ABCDEFGH",
        "firmware": None,
        "vendor": None,
        "protocol": "nvme",
        "capacity_bytes": 0,
    }
    out = render_run_html(run=run, phases=[], timeseries=[], device=device, redact=True)
    assert "<svg/onload=alert(1)>" not in out
    assert "&lt;svg/onload=alert(1)&gt;Samsung" in out
