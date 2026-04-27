# Anvil — NVMe Validator & IOps Lab

[![CI](https://github.com/helixzz/anvil/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/helixzz/anvil/actions/workflows/ci.yml)
[![Release](https://github.com/helixzz/anvil/actions/workflows/release.yml/badge.svg)](https://github.com/helixzz/anvil/actions/workflows/release.yml)
[![Docs](https://github.com/helixzz/anvil/actions/workflows/docs.yml/badge.svg)](https://helixzz.github.io/anvil/)
![version](https://img.shields.io/badge/version-1.3.1-orange)

📚 **Full documentation**: <https://helixzz.github.io/anvil/>

A web-based disk benchmark platform for lab environments. Built for engineers who
frequently swap drives through a dedicated test bench and want to capture,
compare, and track performance in a structured database rather than as one-off
spreadsheets.

Anvil combines:

- **CrystalDiskMark-style preset profiles** for fast sanity checks
- **SNIA SSS PTS-style rigor** (purge → precondition → steady-state detection)
- **Full `fio` sweep coverage** (block size × queue depth × thread count)
- **System-wide environment validation** (CPU governor, PCIe ASPM,
  block-layer tuning, thermal state, idle baseline)
- **Persistent device registry** keyed off stable hardware fingerprints
- **Per-run time-series charts** (IOPS / bandwidth / latency / temperature)
  with phase-boundary annotations
- **Auto-derived sweep charts** (block-size sweep, queue-depth sweep)
- **Device model library** indexed by brand/model, with cross-run
  comparison and headline metrics per test case
- **Stability and thermal scoring** (IOPS CV, temperature range) per
  model, rolled up across all complete runs

The full technical design lives in [`docs/DESIGN.md`](docs/DESIGN.md). The
changelog lives in [`CHANGELOG.md`](CHANGELOG.md).

## Status

Version **0.2.0** — beyond the initial POC. Implemented:

- Device discovery with a multi-layer system-disk guard (mounts, swap,
  DM/LVM/MD holder walk, whole-disk-mount detection).
- 8 benchmark profiles covering non-destructive read sweeps, an
  ezFIO-style destructive sweep, SNIA-flavoured stability, and
  real-world workloads (MySQL OLTP, OLAP scan, VM hosting, video
  editing, desktop general).
- FastAPI backend with WebSocket live updates and a full REST API
  (runs, devices, models, timeseries, phases, compare).
- Privileged runner that reaches into the host's mount namespace via
  `nsenter -t 1 -m` so `lsblk`, `findmnt`, and `nvme list` see the real
  host view.
- React + TypeScript + ECharts UI with English / Chinese i18n, six
  time-series / sweep chart types per run, a models library page, and a
  model detail page with stability and thermal score cards.
- PostgreSQL persistence, Docker Compose deployment.

The roadmap covers true SNIA steady-state convergence, an endurance /
soak profile with thermal auto-pause, a read-only environment-validator
page, cross-model comparison workbench, PDF/ODS/HTML report exports, and
shareable `/r/<slug>` public links — see [`docs/DESIGN.md`](docs/DESIGN.md).

## Hardware and OS requirements

- Linux host with raw block-device access (NVMe, SATA, or SAS).
- Kernel >= 5.4 recommended (io_uring support).
- `fio` >= 3.28, `nvme-cli`, `smartmontools`, `util-linux` (for `lsblk`,
  `findmnt`), `pciutils` (for `lspci`).
- Docker Engine with the Compose plugin, or Podman with `podman compose`.
- Root / `sudo` on the host (the runner container runs privileged so it can
  read `/sys`, `/proc`, and operate raw block devices).

**Safety notice.** Anvil is a benchmarking tool. Benchmark profiles that write
to a drive are destructive: data on the selected drive is overwritten. The tool
refuses to touch block devices that are currently mounted, are part of a swap
area, or back the root filesystem. Destructive runs require explicit typed
confirmation of the device serial number.

## Quick start (development, on the test server itself)

```bash
git clone https://github.com/helixzz/anvil.git
cd anvil

cp .env.example .env
# Optionally edit .env to set ANVIL_BEARER_TOKEN and POSTGRES_PASSWORD.

docker compose up -d --build
```

Then open <http://HOST:8080> in a browser. The default bearer token and a dev
admin account are printed on first startup if you didn't set them in `.env`.

### Without Docker (local hacking)

Backend:

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
export ANVIL_DATABASE_URL=postgresql+asyncpg://anvil:anvil@localhost/anvil
export ANVIL_BEARER_TOKEN=dev-token
export ANVIL_RUNNER_SOCKET=/run/anvil/runner.sock
alembic upgrade head
uvicorn anvil.main:app --reload --host 0.0.0.0 --port 8080
```

Runner (requires root):

```bash
cd runner
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .
sudo mkdir -p /run/anvil && sudo chown "$USER" /run/anvil
sudo ./.venv/bin/anvil-runner --socket /run/anvil/runner.sock
```

Frontend:

```bash
cd frontend
npm install
VITE_API_BASE=http://localhost:8080 npm run dev
```

Open <http://localhost:5173>.

## Project layout

```
anvil/
├── backend/            FastAPI service, SQLAlchemy models, REST + WebSocket API
├── runner/             Privileged worker (UDS RPC, fio invocation, parser)
├── frontend/           React + TypeScript + Vite + ECharts web UI
├── deploy/             docker-compose overlay bits, systemd units, udev rules
├── docs/
│   └── DESIGN.md       Full technical design document
├── scripts/            Helper scripts (device scan, dev bootstrap, etc.)
└── .github/workflows/  Continuous integration
```

## License

MIT — see [LICENSE](LICENSE).
