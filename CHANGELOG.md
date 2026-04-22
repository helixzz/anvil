# Changelog

All notable changes to Anvil are recorded here. Versioning follows
[Semantic Versioning](https://semver.org/) as interpreted for a pre-1.0
project:

- **MINOR** bumps are made for user-visible feature additions, schema
  changes, or material bug fixes.
- **PATCH** bumps are made for internal-only fixes and polish.

## 0.4.0 — 2026-04-22

### Added
- **Cross-model comparison workbench** at `/compare`. Multi-select any
  tested device models, pick a benchmark phase they all share (the
  selector is populated via the new
  `GET /api/models/compare/common-phases?slugs=...` endpoint so phases
  that aren't common to all selections never appear), pick a metric
  (read/write IOPS / BW / mean / p99 latency), and see:
  - A combined bar + scatter chart: two bar series per model (mean and
    best) plus individual-sample scatter points in per-model colour so
    outliers stand out.
  - A per-model summary table with sample count, mean, median, and best.
  Selection is reflected in the URL query string (`?models=...&phase=
  ...&metric=...`) so a comparison view is shareable/bookmarkable.
- `GET /api/models/compare?slugs=...&phase_name=...` returns full samples
  plus a per-model summary (mean/median/best) for each numeric metric.

## 0.3.1 — 2026-04-22

### Changed
- **GitHub Actions CI overhauled**. The workflow now fails loudly on any
  ruff / pytest / typecheck regression (previously pytest was marked
  `continue-on-error` and silently hid failures). New jobs and tightenings:
  - `backend` runs under a Python matrix of 3.11 + 3.12, produces a
    coverage report via `pytest-cov`, and uploads `coverage.xml` as a
    14-day artifact.
  - `runner` runs the same Python matrix and now does an import-smoke that
    imports `server`, `fio`, `discovery`, and the new `env` modules to
    catch NameError / ImportError regressions the ruff pass misses.
  - `frontend` now uploads the Vite `dist/` build as a 14-day artifact.
  - New `version-sync` job asserts that every version string
    (`backend/pyproject.toml`, `runner/pyproject.toml`,
    `frontend/package.json`, plus the two `__version__` dunders) agrees,
    so tag-triggered releases can't ship a mismatched set.
  - New `integration` job stands up the full Docker Compose stack with
    `ANVIL_SIMULATION_MODE=true` (fio `null` ioengine, so the job is
    hermetic and needs no real block devices), waits for the API health
    endpoint, and curls `/api/status`, `/api/runs/profiles`,
    `/api/devices`, `/api/models`, `/api/environment`, and the nginx
    SPA route. This catches Compose/env wiring regressions that unit
    tests can't.
  - Docker builds now use `type=gha` caching for massive cache-hit speedups
    on repeat runs.
- **New `Release` workflow triggers on `v*` tag push**. It first
  re-verifies that the tag's version matches every component (fails the
  release early if versions drift), then extracts the CHANGELOG section
  for the tag, and publishes a proper GitHub Release with the changelog
  as the release body. Pre-release tags (`v1.2.3-rc1`) are marked as
  pre-releases automatically.
- README now carries CI + Release status badges.

### Ops
- This is the first tagged release. Every subsequent milestone will be
  cut as `vX.Y.Z` and tracked in the Releases tab.

## 0.3.0 — 2026-04-22

### Added
- **Latency-distribution chart on run detail**. Picks a phase and renders
  its PDF, CDF, or Exceedance (inverse CDF) curve on a log-log scale,
  overlaying read and write directions. Backed by
  `GET /api/runs/{id}/phases/{phase_id}/histogram`, which parses the
  already-persisted `fio json+` `clat_ns.bins` into histogram + CDF +
  exceedance triples. Requires a fio build with `json+` support
  (installed in the runner image).
- **System environment page** (`/system`). The privileged runner walks
  host `/proc`, `/sys`, and `/proc/1/root` paths (nsenter -t 1 -m) and
  probes CPU frequency governor, turbo/boost state, SMT state, PCIe
  ASPM policy, NVMe APST (`default_ps_max_latency_us`), block-layer
  scheduler and `nr_requests` per attached NVMe, load average, swap
  activity, and the presence + version of `fio`, `nvme`, `smartctl`.
  Each check is surfaced with category, severity, expected value,
  and (where safe) a copy-pastable remediation command. The UI groups
  checks by category with pass/warn/fail/info counts up top, plus a
  "Show issues only" filter. **Read-only for now**; auto-remediation
  is a later roadmap item.
- **Device history page** (`/devices/{id}`). For the selected device,
  plots best read IOPS / write IOPS as bars and best read BW / write
  BW as lines across every completed run, with vertical dashed
  annotations at every firmware change captured in
  `device_snapshots`. Powers the promised regression-tracking flow
  from the design doc.
- **Run abort**. Red "Abort run" button on any non-terminal run detail
  page. Routes through `POST /api/runs/{id}/abort` → orchestrator
  cancels the active `asyncio` task, which closes the RPC stream, which
  makes the runner's fio subprocess receive SIGTERM through
  `os.killpg`. The run is marked `aborted` with `error_message =
  "aborted by user"` and a `run_aborted` event is broadcast to the
  WebSocket so live viewers see the transition immediately.
- **SMART before / after diff** on run detail. Extracts every numeric
  field from `nvme_smart_log`, computes the delta, and renders it with
  colour-coded Δ column (green for "got better", yellow for "went up").
  Temperature values auto-convert from Kelvin to °C for display.
- **Run detail live IOPS / BW / latency / temperature charts updated
  mid-run**, not just after reload. (This line was already shipped in
  0.2.2 but is restated here as part of the 0.3.0 summary because the
  feature set it enables — live observation of long endurance runs —
  matters for every new chart added in this release.)

### Changed
- Devices page model column is now a link into `/devices/{id}` so an
  operator can jump from "which drives are plugged in" straight to
  "how have they performed historically".
- `RunnerClient._call` now accepts a per-call `timeout` kwarg (default
  30 s) so the environment probe can get 60 s to walk `/sys`.

### Notes
- The latency-histogram chart is populated only when fio emits
  `clat_ns.bins`, which is gated by `--output-format=json+`. Older
  runs taken before 0.1.0 may not have the bins; the chart renders a
  "No json+ histogram bins available for this phase" placeholder for
  those.

## 0.2.2 — 2026-04-22

### Fixed
- **Run detail live-update loop that triggered `ERR_INSUFFICIENT_RESOURCES`
  and froze the browser tab.** On a page with an active run, every incoming
  WebSocket frame (a new `phase_sample` every second, a `smart_sample` every
  5 s) fired a React effect whose dependency array included the
  TanStack Query result objects (`runQ`, `phasesQ`, `timeseriesQ`). Those
  objects get a new identity on every render, so calling `.refetch()` inside
  the effect produced a new render, which produced a new dep array, which
  re-ran the effect… 27,254 `/api/runs/{id}/timeseries` requests were fired
  in the first 15 seconds, exhausting the browser's socket pool and
  preventing any follow-up network I/O (including the 2-second polling
  that would otherwise have updated the charts). The user saw stale charts
  that only moved after a manual browser reload.

  The effect now depends only on `events.length` (a primitive), tracks the
  last-processed index in a `useRef`, and uses `queryClient.invalidateQueries()`
  to request a single refetch per `phase_complete` / `run_complete` event
  instead of calling `.refetch()` on captured query objects. Per-second
  chart updates flow through TanStack Query's regular `refetchInterval`
  polling (2 s), plus the WebSocket fast-path nudge for terminal events.
  A long comment in `RunDetail.tsx` documents the exact infinite-loop trap
  so a future maintainer can't accidentally reintroduce it by adding query
  objects back to the dep array.

## 0.2.1 — 2026-04-22

### Added
- **Multi-line profile picker** on the New Run page. The native `<select>`
  truncated profile descriptions (previously clamped to 80 characters
  and collapsed onto a single line). Replaced with a custom
  combobox-style dropdown that shows, on three lines per option:
  - Title (bold) + destructive / read-only badge + estimated duration
    and phase count
  - Full profile description (`.dim`, 12 px)
  The trigger button mirrors the same layout in compact form so the
  closed state remains one row tall. Fully keyboard-accessible: arrow
  keys navigate, Home/End jump to ends, Enter / Space selects, Escape
  closes, Tab closes and moves focus, and clicks outside close the
  popover. ARIA: `role="combobox"` trigger, `role="listbox"` popover,
  `role="option"` items with `aria-selected`, `aria-activedescendant`
  tracking on the listbox. Translations added to both English and
  Chinese locales (`newRun.phasesUnit`, `newRun.destructiveFlag`,
  `newRun.nonDestructiveFlag`).

## 0.2.0 — 2026-04-22

### Added
- **Per-run time-series charts** on the run detail page: live IOPS,
  bandwidth, mean latency, and drive temperature over time. Each chart
  annotates the phase boundaries as vertical dashed lines and now shows
  its current sample count in the chart title for at-a-glance
  diagnostics.
- **Phase-sweep charts** auto-derived from the phase list: block-size
  sweep and queue-depth sweep with log-2 axes and per-pattern colour
  coding. Rendered when three or more phases share the same
  pattern/QD/jobs (or pattern/BS/jobs) tuple.
- **Runner-side SMART polling** every 5 s during a run; NVMe and SATA
  drives both supported. Temperature is persisted into `run_metrics` as
  a run-level series that spans phase transitions.
- **Device model library** under `/models`: indexed by brand and model
  (brand extracted from nvme-cli `ProductName`, so Huawei, Samsung OEM
  drives, DapuStor, and so on are recognised correctly).
- **Model detail page** with device roll-up, all run history, headline
  metrics per phase, a cross-run bar+line comparison chart for any test
  case, and **stability/thermal score cards** (IOPS coefficient of
  variation and temperature range remapped to 0-100).
- **Expanded profile catalog**: in addition to `quick`, the picker now
  offers `standard_read`, `standard`, `mysql_oltp`, `olap_scan`,
  `video_editing`, `desktop_general`, and `stability` — covering the
  non-destructive and destructive tiers described in `docs/DESIGN.md`.
- **Devices page mount-points column** showing every mountpoint (disk
  level and partition level) reported by lsblk for the host's mount
  namespace.
- **Whole-disk-mount exclusion** with a specific reason (e.g. "whole
  device is mounted at /mnt/p4510_4tb") so drives that are formatted and
  mounted directly (no partition table) are clearly non-testable in the
  UI.
- Sidebar now prints both the API version and the web bundle version, so
  a stale cached bundle is obvious at a glance.

### Changed
- Nginx now serves hashed `/assets/` with `Cache-Control: public,
  max-age=31536000, immutable` and `index.html` (plus `/api/`) with
  `Cache-Control: no-store, must-revalidate`. This guarantees a newly
  deployed bundle is picked up on the next page load without manual
  hard-refresh.
- Device fingerprint is now always `sha256(model|serial)`; the WWID is
  still recorded as metadata but no longer affects identity. This
  prevents duplicate rows when a change in tool visibility (e.g.
  switching to nsenter) suddenly starts reporting WWIDs that used to be
  null.
- Discovery runs inside the privileged runner and uses `nsenter -t 1 -m`
  to see the host mount namespace. `lsblk`, `findmnt`, `nvme list`, and
  the `/proc/1/mounts` + `/proc/1/swaps` reads all pick up the host view
  rather than the container's own empty namespace.

### Fixed
- fio's `--status-interval=1` snapshots were being written into the
  `--output=FILE` destination rather than stdout, so the runner's
  depth-tracking parser never saw them and never emitted `phase_sample`
  events. As a result per-second IOPS/BW/latency metrics were not
  persisted. Dropped `--output=FILE`; tee fio's stdout through both the
  live parser and a cumulative buffer that feeds the final summary.
- SQLAlchemy `DateTime` columns were timezone-naive while the codebase
  uses `datetime.now(UTC)`. Every timestamp column is now
  `DateTime(timezone=True)`.
- Host-NS probe previously tried `Path.resolve(strict=True)` on the
  nsfs magic symlink `/proc/1/ns/mnt`, which raised, so the probe always
  returned an empty prefix and `nsenter` was effectively disabled. The
  probe now just checks the symlink and the presence of the `nsenter`
  binary, and short-circuits when the process is already in the host
  mount namespace (bare-metal dev).

## 0.1.0 — 2026-04-22

Initial proof-of-concept release.

- FastAPI backend with SQLAlchemy async + PostgreSQL + WebSocket.
- Privileged runner with Unix-socket JSON-RPC: fio invocation, nvme-cli
  + smartctl wrappers, simulation mode.
- React + TypeScript + Vite + ECharts web UI with English + Chinese
  i18n from day one.
- Quick profile (non-destructive 1 MiB QD8 + 4 KiB QD32 reads).
- Device discovery with partition / mount / swap / DM-stack exclusion.
- docker-compose stack (postgres, api, runner, web) deployable as a
  single unit.
