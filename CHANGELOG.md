# Changelog

All notable changes to Anvil are recorded here. Versioning follows
[Semantic Versioning](https://semver.org/) as interpreted for a pre-1.0
project:

- **MINOR** bumps are made for user-visible feature additions, schema
  changes, or material bug fixes.
- **PATCH** bumps are made for internal-only fixes and polish.

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
