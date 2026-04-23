# HTTP API reference

Anvil exposes a FastAPI-generated OpenAPI schema at
`GET /openapi.json` and an interactive Swagger UI at `GET /docs`
(both are admin-gated on the live deployment).

This page is a hand-curated summary of the most-used endpoints.

## Authentication

All `/api/*` endpoints require either:

- `Authorization: Bearer <ANVIL_BEARER_TOKEN>` (admin automation), or
- `Authorization: Bearer <JWT>` issued by `POST /api/auth/login`

Public `/r/*` endpoints require no authentication.

## Runs

| Method | Path | Role | Description |
|---|---|---|---|
| `GET` | `/api/runs` | viewer | List runs (most recent first) |
| `GET` | `/api/runs/{id}` | viewer | Run detail |
| `POST` | `/api/runs` | operator | Start a new run |
| `POST` | `/api/runs/{id}/abort` | operator | Abort a queued or running run |
| `GET` | `/api/runs/{id}/export.html` | viewer | Self-contained HTML report |
| `GET` | `/api/runs/{id}/export.json` | viewer | Lossless JSON bundle |
| `GET` | `/api/runs/{id}/share` | viewer | Get share status (slug for operator+) |
| `POST` | `/api/runs/{id}/share` | operator | Create or rotate share slug |
| `DELETE` | `/api/runs/{id}/share` | operator | Revoke share slug |
| `GET` | `/api/runs/{id}/timeseries` | viewer | Time-series metrics |
| `GET` | `/api/runs/{id}/phases` | viewer | Per-phase summaries |
| `GET` | `/api/runs/{id}/snia-analysis` | viewer | SNIA steady-state analysis |

## Devices

| Method | Path | Role | Description |
|---|---|---|---|
| `GET` | `/api/devices` | viewer | List discovered devices |
| `POST` | `/api/devices/rescan` | operator | Re-run the runner's device probe |
| `GET` | `/api/devices/{id}/history` | viewer | Run history for one device |

## Models

| Method | Path | Role | Description |
|---|---|---|---|
| `GET` | `/api/models` | viewer | List distinct device models |
| `GET` | `/api/models/{slug}` | viewer | Model detail (aggregated across runs) |
| `GET` | `/api/models/compare` | viewer | Cross-model comparison |

## Saved comparisons

| Method | Path | Role | Description |
|---|---|---|---|
| `GET` | `/api/comparisons` | viewer | List saved comparisons |
| `POST` | `/api/comparisons` | operator | Create |
| `GET` | `/api/comparisons/{id}` | viewer | Fetch one |
| `PUT` | `/api/comparisons/{id}` | operator | Update |
| `DELETE` | `/api/comparisons/{id}` | operator | Delete |
| `POST` | `/api/comparisons/{id}/share` | operator | Create or rotate share slug |
| `DELETE` | `/api/comparisons/{id}/share` | operator | Revoke |

## Environment + auto-tune

| Method | Path | Role | Description |
|---|---|---|---|
| `GET` | `/api/environment` | viewer | Environment check report |
| `GET` | `/api/environment/tune/preview` | admin | Preview tune changes |
| `POST` | `/api/environment/tune/apply` | admin | Apply tune, persist receipt |
| `POST` | `/api/environment/tune/revert` | admin | Revert by `receipt_id` |

## Auth

| Method | Path | Role | Description |
|---|---|---|---|
| `POST` | `/api/auth/login` | (public) | Username + password → JWT |
| `GET` | `/api/auth/me` | viewer | Current principal info |
| `GET` | `/api/auth/sso/config` | admin | Current SSO config (+ version) |
| `PUT` | `/api/auth/sso/config` | admin | Save SSO config (optimistic lock) |
| `POST` | `/api/auth/sso/assertion` | admin | Admin-only SSO provisioning smoke test |

## Admin

| Method | Path | Role | Description |
|---|---|---|---|
| `GET` | `/api/admin/users` | admin | List users |
| `POST` | `/api/admin/users` | admin | Create user |
| `PATCH` | `/api/admin/users/{id}` | admin | Update role/password/active |
| `DELETE` | `/api/admin/users/{id}` | admin | Delete user |

## Dashboard

| Method | Path | Role | Description |
|---|---|---|---|
| `GET` | `/api/dashboard/fleet-stats` | viewer | Summary KPIs |
| `GET` | `/api/dashboard/leaderboards` | viewer | Top-performing models |
| `GET` | `/api/dashboard/pcie-degraded` | viewer | PCIe-degraded runs |
| `GET` | `/api/dashboard/activity` | viewer | N-day run count |
| `GET` | `/api/dashboard/alarms` | viewer | Thermal / failure alerts |

## Public (no auth)

| Method | Path | Description |
|---|---|---|
| `GET` | `/r/runs/{slug}` | Public run report (serial redacted) |
| `GET` | `/r/compare/{slug}` | Public saved-comparison report |

## WebSocket

| Path | Description |
|---|---|
| `/ws/runs/{id}?token=<jwt>` | Live `phase_sample` / `smart_sample` / terminal events |

## Status

| `GET /api/status` | viewer | `{"version", "status", "queued", "running", "runner_ok"}` |
