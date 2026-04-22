# Anvil — NVMe Validator & IOps Lab

A web-based disk benchmark platform for lab environments. Built for engineers who
frequently swap drives through a dedicated test bench and want to capture,
compare, and track performance in a structured database rather than as one-off
spreadsheets.

Anvil combines:

- **CrystalDiskMark-style preset profiles** for fast sanity checks
- **SNIA SSS PTS-style rigor** (purge → precondition → steady-state detection)
- **Full `fio` sweep coverage** (block size × queue depth × thread count)
- **System-wide environment validation and remediation** (CPU governor, PCIe
  ASPM, block-layer tuning, thermal state, idle baseline)
- **Persistent device registry** keyed off stable hardware fingerprints
- **Cross-device comparison, regression tracking, leaderboards, and workload-fit
  scoring**

The full technical design lives in [`docs/DESIGN.md`](docs/DESIGN.md). This
README covers how to run the proof of concept.

## Status

**Proof of concept**. The POC implements the vertical slice described in the
design doc:

- NVMe device discovery with system-disk exclusion
- A **Quick** benchmark profile (sequential 1 MiB QD8 read + random 4 KiB QD32
  read)
- Privileged runner that invokes `fio` and streams progress
- FastAPI backend with WebSocket live updates
- React + TypeScript + ECharts UI with English / Chinese i18n
- PostgreSQL persistence for devices and runs
- Docker Compose deployment

Broader profiles (Standard, SNIA PTS, Endurance), environment validation,
comparison workbench, reports, and vendor-specific SMART plugins are on the
roadmap — see [`docs/DESIGN.md`](docs/DESIGN.md).

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
