# Anvil — NVMe Validator & IOps Lab

![version](https://img.shields.io/badge/version-1.0.1-orange)

**Anvil** is a single-tenant, LAN-deployed benchmark lab for NVMe SSDs.
It orchestrates `fio` runs against raw block devices, captures SMART,
PCIe link state, host-environment fingerprints, and renders both
interactive and printable reports.

## What Anvil does

- **Reproducible benchmark profiles**: `sweep_quick`, `sweep_full`,
  `snia_quick_pts`, `endurance_soak`, with full preconditioning,
  measurement, and cleanup phases.
- **SNIA SSS-PTS v2.0.2 steady-state analysis** on eligible profiles,
  with automatic slope + range gating.
- **Thermal auto-abort**: runs that exceed 75 °C for 6 consecutive
  SMART samples are cancelled.
- **PCIe link capability vs. runtime state** captured per run; drives
  stuck at Gen 4 in a Gen 5 slot light up a degraded-link alert.
- **Cross-model comparison workbench**: multi-select devices, share
  the comparison URL.
- **Public share links** for individual runs and saved comparisons,
  with serial redaction and revocation.
- **Self-contained HTML + JSON run reports** (zero-JS, print-to-PDF).
- **RBAC (viewer / operator / admin)** with bcrypt passwords and
  JWTs.
- **Admin-configurable SSO** with group→role mapping (ACS still
  out of scope at 1.0.0).
- **One-click environment auto-tune** with receipt-ID-based revert.
- **Crash-safe orchestrator** with startup reconciliation of in-flight
  runs.

## Who it's for

Hardware validation teams, firmware engineers, and storage performance
testers who need **reproducible results, not dashboards**. Anvil is
intentionally narrow: one device under test at a time, raw block
devices only, LAN-only deployment, no multi-tenancy.

## Quick links

- [**Install Anvil**](getting-started/install.md)
- [**Run your first benchmark**](getting-started/first-run.md)
- [**Read a run report**](user-guide/reports.md)
- [**API reference**](reference/api.md)
- [**CHANGELOG**](CHANGELOG.md)

## Safety

Anvil writes to raw block devices. Destructive profiles require the
last 6 characters of the device serial as a confirmation token before
the run starts. Do not point Anvil at a filesystem-mounted device or a
production drive.
