# Installation

Anvil ships as a Docker Compose stack with three services: the
FastAPI backend (`api`), the React web frontend (`web`), and the
privileged runner (`runner`). Postgres (`db`) is the fourth container.

## Prerequisites

- Linux host with Docker 24+ and Docker Compose v2
- `sudo` privilege for the runner container (it needs `--privileged`
  + `pid=host` + host namespace access to run `fio`, `nvme`, and
  `lspci` against real devices)
- A raw, unmounted NVMe block device you're willing to have Anvil
  write to

## Clone and start

```bash
git clone https://github.com/helixzz/anvil
cd anvil
cp .env.example .env
# Edit .env — at minimum set ANVIL_BEARER_TOKEN to a random string of 32+ chars
sudo docker compose up -d
```

Anvil will be reachable at `http://localhost:8081` (web) and
`http://localhost:8080` (API).

## Environment variables

The `.env` file controls configuration:

| Variable | Default | Description |
|---|---|---|
| `ANVIL_BEARER_TOKEN` | *(required)* | Admin bearer token; also the bootstrap admin password (first 16 chars) |
| `ANVIL_DATABASE_URL` | `postgresql+asyncpg://anvil:anvil@db:5432/anvil` | Postgres async DSN |
| `ANVIL_RUNNER_SOCKET` | `/run/anvil/runner.sock` | Unix socket for runner RPC |
| `ANVIL_CORS_ORIGINS` | `[]` | JSON array of allowed origins; empty disables CORS entirely |
| `ANVIL_LOG_LEVEL` | `info` | Log level |
| `ANVIL_SIMULATION_MODE` | `false` | Stub runner responses for UI development |

## First admin login

Anvil bootstraps a default admin user on first boot:

- Username: `admin`
- Password: first 16 characters of `ANVIL_BEARER_TOKEN`

Rotate this password immediately from the Admin → Users page.

The legacy bearer token remains valid as an admin credential for
automation.

## Production notes

- Anvil assumes a **trusted LAN**. HTTPS is not a built-in concern;
  terminate TLS at an upstream reverse proxy if you need it.
- The runner container must be the only host process writing to the
  device under test. Anvil rejects runs against mounted filesystems
  and against devices without an empty partition table.
- Postgres is plain 16-alpine; back it up like any other database.
