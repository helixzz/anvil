# Anvil — Technical Design

This document captures the design of the Anvil storage benchmark platform. The
current codebase implements a proof-of-concept vertical slice; this document is
the target state everything is building toward.

## 1. Vision

A single-server web-based storage benchmarking platform for laboratory
environments. Engineers frequently swap drives (NVMe, SATA, SAS) through a
dedicated test bench. Anvil maintains a persistent database of every device
ever tested, every benchmark run, the full environmental context each run was
captured in, and the tools for comparing, tracking, and reporting on that
history.

The platform combines:

- **CrystalDiskMark's accessibility** — preset profiles, one-click runs.
- **SNIA SSS PTS v2.0.2 rigor** — purge, preconditioning, steady-state
  convergence detection, workload matrices.
- **ezFIO-style full sweeps** — block size × queue depth × thread count.
- **Modern web UX** — live WebSocket progress, interactive charts,
  regression alerts, cross-device comparison.
- **Enterprise-grade safety** — system-disk guard, typed confirmation of
  destructive ops, full audit logging.

## 2. Deployment model

Single-tenant, trusted LAN deployment:

- All services run on one physical test server as Docker containers.
- Authentication is a single bearer token; no RBAC for v1.
- The server is dedicated to testing; the block devices being tested are also
  physically attached to the same host.
- Tests execute **serially** under a global lock to eliminate PCIe, CPU, and
  thermal contention that would compromise measurement reproducibility.

## 3. High-level architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (React + TypeScript + Vite + ECharts)                  │
└────────────────────────▲────────────────────────────────────────┘
                         │ HTTPS / WebSocket
┌────────────────────────┴────────────────────────────────────────┐
│  FastAPI (Python 3.12, uvicorn)                                  │
│  ├─ REST /api/*       CRUD, discovery, profiles, runs            │
│  ├─ WS   /ws/runs/{id} Live progress                             │
│  └─ Auth: bearer token                                           │
└──────────┬─────────────────────┬──────────────────────────────────┘
           │                     │
┌──────────┴─────────┐  ┌───────┴────────────────┐
│  Orchestrator       │  │  Device discovery       │
│  (asyncio)          │  │  (nvme-cli, smartctl,   │
│  ├─ Job queue       │  │   lsblk, findmnt)       │
│  ├─ Env validator   │  │                         │
│  └─ RPC → runner    │  └───────────────────────┘
└──────────┬─────────┘
           │ Unix domain socket (signed JSON-RPC)
┌──────────┴────────────┐
│  Runner (privileged)   │
│  ├─ fio subprocess     │
│  ├─ nvme-cli wrappers  │
│  └─ sysfs read/write   │
└───────────────────────┘
           │
┌──────────┴─────────┐
│  PostgreSQL 16     │   (TimescaleDB extension for time-series)
│  + filesystem      │
│    (raw fio logs,  │
│     reports)       │
└────────────────────┘
```

Key decisions:

- **Runner is an isolated process** on a Unix domain socket. Only the runner is
  privileged; the API/UI run unprivileged. The API cannot open raw block
  devices directly. This keeps the blast radius minimal.
- **Postgres + TimescaleDB** for relational data and per-second time-series in
  one database. Per-second metrics get compressed after a configurable window.
- **WebSocket fan-out** is in-process via an asyncio pub/sub on the API
  process; the runner pushes events over the UDS and the API rebroadcasts.

## 4. Device registry and discovery

Discovery runs on API startup, on-demand, and (in later phases) on every
`udev` add/remove event.

Per block device we collect:

- **Identity**: model, serial, firmware, WWID, PCIe BDF, link speed / width,
  ASPM state, NUMA node, form factor.
- **Capabilities**: LBA formats, protection information, secure-erase support,
  sanitize support, APST state, OCP telemetry version.
- **Health snapshot**: SMART or NVMe smart-log, parsed into a normalized form
  plus stored in full as JSONB for future reprocessing by vendor plugins.

**System-disk guard** (every device must pass all of these before becoming
testable):

1. Not mounted (`/proc/mounts`, `findmnt`).
2. Not a swap backing store (`/proc/swaps`).
3. Not a holder or parent of a mounted device-mapper / LVM / MD / ZFS device
   (walks `/sys/block/*/holders`).
4. Not the root-filesystem source (`findmnt -n -o SOURCE /` walking any DM/LVM
   stack).

A **stable fingerprint** is derived from WWID when available, otherwise
`sha256(model + serial)`. Re-insertion of the same drive matches back to its
historical record.

## 5. Test catalog

| Tier          | Duration     | Purpose                                                           |
| ------------- | ------------ | ----------------------------------------------------------------- |
| Quick         | 5 – 15 min   | Sanity / CrystalDiskMark-equivalent.                              |
| Standard      | 30 – 90 min  | Block-size sweep + QD sweep + mixed + 20 min stability.           |
| SNIA PTS Full | 4 – 24 h     | Purge, workload-independent precondition, steady-state matrix.    |
| Endurance     | Days         | Sustained random write until target TBW, with thermal pauses.     |
| Custom        | User-defined | Visual workload builder.                                          |

The Quick profile is implemented in the POC. The rest are sketched in the
`backend/anvil/profiles/` directory for expansion.

### 5.1 fio invocation

fio job files are generated from Jinja2 templates. We always use
`--output-format=json+` to capture latency histogram bins. We also stream
`--status-interval=1` JSON to stdout for live progress, split on object
boundaries (documented fio caveat), and emit it to WebSocket subscribers and
the metrics hypertable.

### 5.2 Steady-state convergence (future)

The SNIA profile adds a convergence tracker with SNIA's canonical criteria:

- Range: `(max − min) ≤ 20 %` of the SSMW average.
- Slope: linear-regression total drift across the 5-round window
  `≤ 10 %` of the SSMW average.

Declare steady state when both hold; otherwise continue rounds up to a safety
cap (default 25) and label the run "did not converge".

## 6. Data model (summarised)

- `devices` — one row per unique physical device (fingerprint).
- `device_snapshots` — point-in-time hardware/SMART capture.
- `test_profiles` — reusable profile definitions.
- `runs` — one execution of a profile against a device; holds `env_before`,
  `env_after`, `smart_before`, `smart_after`, `host_system`, and a frozen
  `profile_snapshot`.
- `run_phases` — per-phase fio JSON plus extracted scalar metrics for fast
  comparisons.
- `run_metrics` — TimescaleDB hypertable for per-second IOPS / BW / latency.
- `latency_histograms` — sparse bin counts from fio `json+`.
- `audit_log` — every destructive action and remediation.

See `backend/alembic/versions/` for the actual migration scripts.

## 7. Environment validation and remediation

Separate category document (`docs/ENV_CHECKS.md`) lists every pre-flight
check: CPU governor, turbo / C-state state, PCIe ASPM (global and per-device),
NVMe APST, IRQ affinity, NUMA locality, block-layer scheduler / `nr_requests`
/ `rq_affinity`, baseline CPU and memory idle, thermal state, filesystem
safety, kernel / tool versions, and security-mitigation state.

Remediations fall into three tiers:

1. **Ephemeral** — sysfs writes. Captured-before and reverted at run end.
2. **Session** — running agents holding references (e.g. `cpupower
   idle-set -D0`). Reverted on shutdown.
3. **Persistent** — generated udev rules and GRUB snippets. Always requires
   explicit operator confirmation with a diff preview and can be reverted from
   the UI.

## 8. Comparison, reports, sharing

- **Workbench** — overlay N runs across any metric (IOPS, BW, mean latency,
  percentile latency), any axis (BS, QD, threads, time-in-run), and any chart
  (line, bar, heatmap, radar, 3-D surface).
- **Regression** — per-device history with firmware-change annotations. A
  result that deviates > 10 % from the rolling median on a top-line metric is
  flagged.
- **Fit score** — per workload profile, geometric mean of peer-group
  percentile ranks. Radar chart per drive.
- **Reports** — interactive HTML (the UI itself), PDF (WeasyPrint or Playwright
  headless), OpenDocument (for ezFIO compatibility), CSV / JSON bundle.
- **Sharing** — signed non-guessable URLs for individual runs and saved
  comparisons.

## 9. Safety gates

- System-disk exclusion is enforced at discovery time and re-checked
  immediately before any destructive operation.
- Typed confirmation of the last 6 characters of the device serial number.
- 10-second countdown with abort.
- Rate limit of 1 destructive run start per 30 seconds.
- Audit log row per destructive action, including actor, target, profile, and
  timestamp.
- Simulation mode: drive into the full pipeline with fio's `null` ioengine,
  touching no storage.

## 10. Extensibility

Entry-point based plugin system:

- `anvil.profiles` — additional test profiles.
- `anvil.extractors` — vendor-specific SMART parsing (Intel, Samsung, WDC,
  Micron, …).
- `anvil.exporters` — extra report formats.
- `anvil.env_checks` — site-specific environment checks (e.g. rack temp from
  IPMI).
- `anvil.notifications` — webhook / Slack / email on completion or
  regression.

## 11. Roadmap

Version history lives in [`CHANGELOG.md`](CHANGELOG.md).

1. **POC (0.1.0, shipped)**: discovery, Quick profile, live WebSocket chart,
   saved report.
2. **Analytics foundation (0.2.0, shipped)**: runner-side SMART polling,
   per-run time-series charts (IOPS/BW/lat/temperature) with phase-boundary
   annotations, auto-derived block-size and queue-depth sweep charts, an
   expanded 8-profile catalog covering read-only, destructive, and workload
   presets, a model library (`/models`) with cross-run comparison charts and
   stability/thermal scoring per model, host-namespace discovery for correct
   system-disk exclusion, and nginx cache-control so fresh deploys take effect
   immediately.
3. **Steady-state & endurance**: true SNIA convergence loop driving a `snia_pts`
   profile; endurance profile with thermal auto-pause; WSAT-style write
   saturation tracking.
4. **Environment validator**: read-only page surfacing every CPU-governor /
   ASPM / irqbalance / block-layer / thermal check, with opt-in
   auto-remediation wrapped in a revert-on-exit transaction.
5. **Analytics II**: latency histograms from `fio json+` bins, cross-model
   comparison workbench, workload-profile fit scores, anomaly detection.
6. **Polish & extensibility**: custom visual profile builder, vendor-specific
   SMART plugins (Intel / Samsung / WDC / Micron / …), scheduled recurring
   runs, PDF / ODF / HTML report exports, shareable `/r/<slug>` public links.

## 12. Non-goals

- Multi-tenant or public-internet deployment.
- Cloud storage benchmarking (S3 / object / file-system only tests).
- Replacement for vendor qualification suites.

## 13. Versioning

All three components (`backend/pyproject.toml`, `runner/pyproject.toml`,
`frontend/package.json`) share a single version string and bump together. The
Python `__version__` constants in `backend/anvil/__init__.py` and
`runner/anvil_runner/__init__.py` must match, and the frontend surfaces both
`api` and `web` versions in the sidebar so an operator can spot a stale cached
bundle at a glance.

Rule: every meaningful change (user-visible behaviour, schema, or material bug
fix) bumps the MINOR component and appends an entry to `CHANGELOG.md`.
Internal-only fixes bump the PATCH component.
