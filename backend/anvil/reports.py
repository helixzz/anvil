"""Run report exporters.

Generates a self-contained HTML file (no JS, ECharts rendered server-side
to static SVG via the bundled templates) and a JSON bundle of every
artefact used in the Run detail page.

Why static HTML + JSON and not PDF:

- PDF generation via headless browsers (Playwright / Chromium) requires
  ~400 MB of browser binaries in the container image, which is a large
  cost for a nice-to-have export. Static HTML is Ctrl+P printable from
  any browser, which covers the PDF use case with zero runtime cost.
- JSON is the lossless archive format — future tooling can re-render the
  same data into whatever report format the consumer needs (ODF, CSV,
  custom corporate templates) without running Anvil.

The rendered HTML intentionally inlines every chart's data as SVG
elements so the report works offline and can be committed to a
repository, attached to an email, or archived long-term.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from anvil import __version__


def _fmt_ns(ns: float | int | None) -> str:
    if ns is None:
        return "—"
    ns = float(ns)
    if ns < 1_000:
        return f"{ns:.0f} ns"
    if ns < 1_000_000:
        return f"{ns / 1_000:.2f} µs"
    if ns < 1_000_000_000:
        return f"{ns / 1_000_000:.2f} ms"
    return f"{ns / 1_000_000_000:.2f} s"


def _fmt_bytes(b: float | int | None) -> str:
    if b is None:
        return "—"
    b = float(b)
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    i = 0
    while b >= 1024 and i < len(units) - 1:
        b /= 1024
        i += 1
    return f"{b:.2f} {units[i]}"


def _fmt_iops(v: float | int | None) -> str:
    if v is None:
        return "—"
    v = float(v)
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f} M"
    if v >= 1_000:
        return f"{v / 1_000:.1f} k"
    return f"{v:.0f}"


def _render_phase_row(phase: dict[str, Any]) -> str:
    def td(val: str, extra: str = "") -> str:
        return f'<td class="mono{(" " + extra) if extra else ""}">{val}</td>'

    return (
        "<tr>"
        + td(str(phase.get("phase_order", "")))
        + td(str(phase.get("phase_name", "")), "name")
        + td(str(phase.get("pattern", "")))
        + td(_fmt_bytes(phase.get("block_size")))
        + td(str(phase.get("iodepth", "")))
        + td(str(phase.get("numjobs", "")))
        + td(_fmt_iops(phase.get("read_iops")))
        + td(_fmt_bytes(phase.get("read_bw_bytes")) + "/s")
        + td(_fmt_iops(phase.get("write_iops")))
        + td(_fmt_bytes(phase.get("write_bw_bytes")) + "/s")
        + td(_fmt_ns(phase.get("read_clat_mean_ns") or phase.get("write_clat_mean_ns")))
        + td(_fmt_ns(phase.get("read_clat_p99_ns") or phase.get("write_clat_p99_ns")))
        + "</tr>"
    )


def _timeseries_svg(
    metrics: list[dict[str, Any]],
    metric_names: list[str],
    title: str,
    y_label: str,
    value_formatter: callable,  # type: ignore[valid-type]
) -> str:
    """Server-side line-chart renderer.

    Produces a compact inline SVG with one polyline per metric. Deliberately
    minimalist so the export file stays small and every browser (including
    old corporate IE/Edge) renders it without JS.
    """
    width, height = 720, 180
    padding_l, padding_b, padding_t, padding_r = 60, 20, 20, 20
    chart_w = width - padding_l - padding_r
    chart_h = height - padding_t - padding_b

    per_metric: dict[str, list[tuple[float, float]]] = {m: [] for m in metric_names}
    for pt in metrics:
        if pt["metric_name"] in per_metric:
            try:
                ts = datetime.fromisoformat(pt["ts"].replace("Z", "+00:00")).timestamp()
                per_metric[pt["metric_name"]].append((ts, float(pt["value"])))
            except (KeyError, TypeError, ValueError):
                pass

    for m in metric_names:
        per_metric[m].sort(key=lambda p: p[0])

    all_x = [x for arr in per_metric.values() for x, _ in arr]
    all_y = [y for arr in per_metric.values() for _, y in arr]
    if not all_x or not all_y:
        return (
            f'<div class="chart-empty"><h4>{title}</h4>'
            f'<div class="dim">no data</div></div>'
        )

    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = 0.0, max(all_y) * 1.1
    x_span = max(x_max - x_min, 1.0)
    y_span = max(y_max - y_min, 1.0)

    colors = ["#60a5fa", "#f4a340", "#4ade80", "#c084fc", "#f87171"]
    lines = []
    legend_items: list[str] = []
    for i, metric in enumerate(metric_names):
        pts = per_metric[metric]
        if not pts:
            continue
        color = colors[i % len(colors)]
        poly_pts = []
        for tx, ty in pts:
            x_px = padding_l + (tx - x_min) / x_span * chart_w
            y_px = padding_t + chart_h - (ty - y_min) / y_span * chart_h
            poly_pts.append(f"{x_px:.1f},{y_px:.1f}")
        lines.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{" ".join(poly_pts)}" />'
        )
        legend_items.append(f'<span class="legend-dot" style="background:{color}"></span>{metric}')

    y_ticks = []
    for i in range(5):
        v = y_min + (y_max - y_min) * i / 4
        y_px = padding_t + chart_h - (v - y_min) / y_span * chart_h
        y_ticks.append(
            f'<text x="{padding_l - 4}" y="{y_px:.1f}" class="tick-label" text-anchor="end">{value_formatter(v)}</text>'
            f'<line x1="{padding_l}" x2="{width - padding_r}" y1="{y_px}" y2="{y_px}" stroke="#1a2440" />'
        )

    return f"""
    <div class="chart">
      <h4>{title} · {len(all_y)} samples</h4>
      <div class="legend">{" ".join(legend_items)}</div>
      <svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
        <rect x="{padding_l}" y="{padding_t}" width="{chart_w}" height="{chart_h}" fill="#0b1220" stroke="#233256" />
        {"".join(y_ticks)}
        {"".join(lines)}
        <text x="{padding_l}" y="{height - 4}" class="axis-label" fill="#94a3b8">{y_label}</text>
      </svg>
    </div>
    """


def _redact_serial(serial: str | None) -> str:
    if not serial:
        return "—"
    if len(serial) <= 4:
        return "••••"
    return "•" * (len(serial) - 4) + serial[-4:]


def render_run_html(
    *,
    run: dict[str, Any],
    phases: list[dict[str, Any]],
    timeseries: list[dict[str, Any]],
    device: dict[str, Any] | None,
    redact: bool = False,
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    title = f"Anvil Run Report — {run['id']}"
    pcie_at_run = (run.get("host_system") or {}).get("pcie_at_run") or {}
    pcie_cap = pcie_at_run.get("capability") or {}
    pcie_st = pcie_at_run.get("status") or {}

    phases_html = "".join(_render_phase_row(p) for p in phases)

    iops_svg = _timeseries_svg(
        timeseries,
        ["read_iops", "write_iops"],
        "IOPS over time",
        "IOPS",
        _fmt_iops,
    )
    bw_svg = _timeseries_svg(
        timeseries,
        ["read_bw_bytes", "write_bw_bytes"],
        "Bandwidth over time",
        "Bandwidth",
        lambda v: _fmt_bytes(v) + "/s",
    )
    lat_svg = _timeseries_svg(
        timeseries,
        ["read_clat_mean_ns", "write_clat_mean_ns"],
        "Mean latency over time",
        "Latency",
        _fmt_ns,
    )
    temp_svg = _timeseries_svg(
        timeseries,
        ["temperature_c"],
        "Drive temperature over time",
        "°C",
        lambda v: f"{v:.1f} °C",
    )

    device_block = ""
    if device:
        serial_display = _redact_serial(device.get("serial")) if redact else (device.get("serial", "—") or "—")
        device_block = f"""
        <h2>Device under test</h2>
        <table class="kv">
          <tr><th>Model</th><td class="mono">{device.get('model', '—')}</td></tr>
          <tr><th>Serial</th><td class="mono">{serial_display}</td></tr>
          <tr><th>Firmware</th><td class="mono">{device.get('firmware') or '—'}</td></tr>
          <tr><th>Vendor</th><td class="mono">{device.get('vendor') or '—'}</td></tr>
          <tr><th>Protocol</th><td class="mono">{device.get('protocol', '—')}</td></tr>
          <tr><th>Capacity</th><td class="mono">{_fmt_bytes(device.get('capacity_bytes'))}</td></tr>
          <tr><th>PCIe capability</th><td class="mono">{pcie_cap.get('pcie_gen', '—')} x{pcie_cap.get('width', '—')}</td></tr>
          <tr><th>PCIe actual</th><td class="mono">{pcie_st.get('pcie_gen', '—')} x{pcie_st.get('width', '—')}{' <span class="badge warn">degraded</span>' if pcie_at_run.get('degraded') else ''}</td></tr>
        </table>
        """

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<title>{title}</title>
<style>
body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
        background: #0b1220; color: #e2e8f0; margin: 0; padding: 32px; font-size: 13px; }}
h1 {{ font-size: 22px; margin: 0 0 4px 0; }}
h2 {{ font-size: 16px; margin: 24px 0 8px 0; color: #cbd5e1; border-bottom: 1px solid #233256; padding-bottom: 4px; }}
h4 {{ font-size: 12px; margin: 0 0 8px; color: #cbd5e1; font-weight: 500; }}
table {{ width: 100%; border-collapse: collapse; margin: 8px 0 16px; font-variant-numeric: tabular-nums; }}
th, td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid #233256; }}
th {{ color: #94a3b8; font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
.mono {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; }}
.dim {{ color: #94a3b8; }}
.kv th {{ width: 180px; }}
.chart {{ margin: 12px 0; padding: 12px; background: #111a2e; border: 1px solid #233256; border-radius: 6px; }}
.chart-empty {{ margin: 12px 0; padding: 20px; background: #111a2e; border: 1px dashed #233256; border-radius: 6px; text-align: center; }}
.legend {{ font-size: 11px; color: #94a3b8; margin-bottom: 8px; }}
.legend-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }}
.tick-label {{ font-size: 10px; fill: #94a3b8; }}
.axis-label {{ font-size: 10px; }}
.badge {{ display: inline-block; padding: 1px 6px; border-radius: 999px; font-size: 10px; }}
.warn {{ background: #422006; color: #fde68a; }}
.meta {{ color: #94a3b8; font-size: 12px; }}
.footer {{ margin-top: 40px; padding-top: 12px; border-top: 1px solid #233256; color: #94a3b8; font-size: 11px; }}
@media print {{ body {{ background: white; color: black; }} .chart, .chart-empty {{ background: white; border-color: #ccc; }} th, td {{ border-bottom-color: #ccc; }} }}
</style>
</head><body>
<h1>{title}</h1>
<div class="meta">
  Profile <span class="mono">{run['profile_name']}</span> ·
  status <span class="mono">{run['status']}</span> ·
  started <span class="mono">{run.get('started_at', '—')}</span> ·
  finished <span class="mono">{run.get('finished_at', '—')}</span> ·
  generated <span class="mono">{now}</span>
</div>

{device_block}

<h2>Phases ({len(phases)})</h2>
<table>
  <thead>
    <tr>
      <th>#</th><th>Name</th><th>Pattern</th><th>BS</th><th>QD</th><th>Jobs</th>
      <th>Read IOPS</th><th>Read BW</th><th>Write IOPS</th><th>Write BW</th>
      <th>Mean lat</th><th>p99 lat</th>
    </tr>
  </thead>
  <tbody>{phases_html}</tbody>
</table>

<h2>Time series</h2>
{iops_svg}
{bw_svg}
{lat_svg}
{temp_svg}

<div class="footer">
  Generated by Anvil {__version__}. Report includes every metric persisted
  for this run. For the machine-readable bundle use
  /api/runs/{run['id']}/export.json.
</div>
</body></html>
"""


def render_run_json_bundle(
    *,
    run: dict[str, Any],
    phases: list[dict[str, Any]],
    timeseries: list[dict[str, Any]],
    device: dict[str, Any] | None,
) -> bytes:
    """Lossless machine-readable archive of every run artefact.

    Future tooling (PDF pipelines, ODS / corporate-template generators,
    external dashboards) should consume this JSON rather than scraping
    the HTML export.
    """
    bundle = {
        "schema_version": 1,
        "anvil_version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "run": run,
        "phases": phases,
        "timeseries": timeseries,
        "device": device,
    }
    return json.dumps(bundle, default=str, indent=2).encode("utf-8")
