# Reading a report

Every completed run has a Run Detail page showing:

## Topbar

- Run status, profile, device path
- Start / finish timestamps
- **Abort** (while running)
- **Export HTML** / **Export JSON** (see [sharing](sharing.md))
- **Share link** (operator+admin) to create a public URL

## KPI cards

Six summary cards showing the highest-numbered measurement phase's:

- Read IOPS / BW
- Write IOPS / BW
- Read mean latency / p99

These are convenience cards. The per-phase table below is authoritative.

## PCIe link card

- **Capability**: what the endpoint advertises (e.g. Gen 5 x4)
- **Actual at run time**: what the link trained to (e.g. Gen 4 x4)
- **Degraded badge** if capability > actual

A common cause of a degraded link is the motherboard trace-length
budget on older slots; the drive itself is fine. Anvil's point here
is to make you aware so you don't publish "Gen 5 numbers" when the
link is running Gen 4.

## Phase table

One row per phase in run order:

| # | Name | Pattern | BS | QD | Jobs | Read IOPS | Read BW | Write IOPS | Write BW | Mean lat | p99 lat |

## Time series

Four inline charts (server-rendered SVG in the export, ECharts in
the UI):

1. **IOPS over time** (read / write)
2. **Bandwidth over time**
3. **Mean latency over time**
4. **Drive temperature over time**

Watch the temperature chart during long-running workloads. A rising
slope that doesn't plateau is a warning sign for thermal throttling.

## SMART before / after

Every integer-valued SMART field is shown with before / after / delta.
Counter fields (`data_units_written`, `media_errors`, etc.) are the
useful ones — big deltas on `media_errors` during a run mean the
drive is in trouble.

## Latency distribution

For any selected phase, histograms rendered from fio's `json+`
clat_hist bins:

- **PDF** (density)
- **CDF** (cumulative)
- **Exceedance** (inverse CDF) — for tail-latency hunting

Some profiles don't emit json+ histograms; the widget says so if the
bins aren't available.

## SNIA steady-state card

Only appears on SNIA profiles. Shows:

- Window mean across the last 5 rounds
- Max range %
- Slope %
- Pass/fail per gate

See [profiles](profiles.md) for the gate definitions.
