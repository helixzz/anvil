# Changelog

All notable changes to Anvil are recorded here. Versioning follows
[Semantic Versioning](https://semver.org/):

- **MAJOR** bumps for breaking API or on-disk format changes.
- **MINOR** bumps for user-visible feature additions and schema changes.
- **PATCH** bumps for internal-only fixes and polish.

## 1.2.0 — 2026-04-23

### Added
- **Physical slot / tray mapping per device.** Every device now has
  an operator-editable `physical_location` field holding
  `{chassis, bay, tray, port, notes}`. A new
  `PhysicalLocationCard` on the Device Detail page lets operators
  annotate where each drive lives in the rack and surfaces the
  auto-detected PCIe BDF address (stable across reboots) so a drive
  can be physically identified without opening the chassis.
- New endpoint `PATCH /api/devices/{id}/location` (operator+admin)
  accepts the five fields; empty strings are treated as "unset" and
  an empty payload clears the location. Persisted via new column
  `devices.physical_location` (nullable JSONB, migration
  `20260423_0006_physical_location`).
- `DeviceOut` schema + API client gain `physical_location`.
- 5 new tests covering set / clear / 404 / empty-string handling /
  round-trip read (96 total).

### Migrations
- **`20260423_0006_physical_location`** — adds nullable JSONB
  column `devices.physical_location`.

## 1.1.0 — 2026-04-23

### Added
- **Hosted documentation site** at
  <https://helixzz.github.io/anvil/>. Built with MkDocs Material,
  deployed from `main` on any `docs/**` or `mkdocs.yml` change via a
  new `docs` GitHub Actions workflow that publishes to GitHub Pages.
  Contents:
  - Getting Started: installation, first run
  - User Guide: profiles, running, reading reports, compare,
    public share links
  - Operator Guide: RBAC, SSO, env-tune, crash recovery, security
  - Reference: HTTP API summary, CHANGELOG, design doc
- README gains a badge and direct link to the docs site.

## 1.0.1 — 2026-04-23

### Added
- **"Share view" button on the Compare page.** Copies the current URL
  (with `models=`, `phase=`, `metric=` query-string state) to the
  clipboard so anyone with access to the lab can reproduce the same
  comparison view. Falls back to a prompt when the Clipboard API is
  blocked (non-HTTPS LAN deployments, older browsers).

## 1.0.0 — 2026-04-23

First stable release. Anvil 1.0.0 is the culmination of 17 cycles of
feature and hardening work. The public HTTP API, the runner RPC, the
on-disk schema (including all Alembic migrations through
`20260423_0005_tune_receipts`), the profile contract, and the report
export formats are now considered stable; backwards-incompatible
changes to any of these will force a MAJOR bump.

### What's in the box
- **Benchmark profiles**: `sweep_quick`, `sweep_full`,
  `snia_quick_pts`, `endurance_soak`, plus the standard precondition
  / measurement / cleanup phase model. Every profile runs
  `fio --output-format=json+` in the privileged runner container.
- **SNIA SSS-PTS v2.0.2 steady-state**: automatic IOPS / latency /
  bandwidth steady-state evaluation on eligible profiles with slope
  + range gates and a SniaAnalysisCard on Run Detail.
- **Thermal auto-abort**: runs that exceed 75 °C for 6 consecutive
  SMART samples are cancelled with a `thermal_abort` reason.
- **PCIe link reporting**: every run captures device capability vs.
  runtime link state from `lspci -vvv`; degraded-link warning on
  Run, Device, and Dashboard.
- **Cross-model comparison** (`/compare`): multi-select runs,
  common-phase intersection, bar + scatter overlay, URL-state sync.
- **Saved comparisons + public share links** (`/r/runs/{slug}`,
  `/r/compare/{slug}`): serial-redacted, zero-JS, strict-CSP public
  HTML views; revocable.
- **Run report exports**: self-contained HTML (SVG charts, print to
  PDF) and lossless JSON bundle per run; via authenticated API and
  revocable public share links.
- **Overview dashboard**: 6 KPI cards, PCIe-degraded alert,
  alarms, 30-day activity, 4 leaderboards, recent runs.
- **RBAC**: viewer / operator / admin with bcrypt passwords and
  12 h HS256 JWTs. Bootstrap `admin` user auto-created on first
  boot; `/admin/users` CRUD for admins.
- **Admin-configurable SSO** with group→role mapping and
  optimistic-locking on concurrent config edits. Note: the
  production SAML ACS is out of scope for 1.0.0; the
  `/api/auth/sso/assertion` endpoint is an admin-only smoke test
  that never accepts unauthenticated callers.
- **One-click environment auto-tune**: 5 host tunables
  (cpu governor, PCIe ASPM, NVMe scheduler / nr_requests /
  read-ahead) with server-side persisted receipts; revert by
  opaque `receipt_id`, path-allowlist enforced inside the runner.
- **Crash-safe orchestrator**: explicit terminal-event contract with
  the runner (EOF / timeout → failed, never silently complete), DB
  outage fault-isolation in the worker loop, and startup
  reconciliation for stranded `queued` / `preflight` / `running`
  rows.
- **i18n**: English + Chinese across every UI string.
- **CI**: ruff + 86 pytest tests on Python 3.11 + 3.12, full
  frontend build, Compose integration smoke test, version-sync gate.

### Security posture at 1.0.0
- Every interpolated value in report HTML is `html.escape()`'d.
- Public share responses carry a strict Content-Security-Policy plus
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `X-Robots-Tag: noindex`.
- Share slugs are 128-bit `secrets.token_urlsafe(16)` tokens; the
  active slug is disclosed only to operator+admin roles.
- Env-tune revert never accepts client-supplied paths; the runner
  refuses any write outside a sysfs-glob allowlist.
- CORS defaults to an empty origin list (middleware not installed);
  wildcard + credentials is downgraded with a warning.

### Backwards-compatibility notes for operators
- Alembic heads: `20260423_0005`. Upgrade from any 0.x with
  `alembic upgrade head`.
- The legacy bearer token (`ANVIL_BEARER_TOKEN`) remains a valid
  admin credential for automation.
- The frontend vendor bundle is now code-split; deployments behind a
  cache must invalidate the `dist/assets/` prefix on upgrade.

## 0.17.0 — 2026-04-23

### Security
- **CORS default tightened.** `cors_origins` previously defaulted to
  `["*"]` with `allow_credentials=True`, a combination browsers
  silently refuse to honor for credentialed XHR; the default is now
  an empty list so the CORS middleware is not installed at all
  unless an operator explicitly lists the origins they need. If an
  operator still sets `["*"]`, `allow_credentials` is forced to
  `False` and a warning log is emitted. Allowed methods/headers were
  also narrowed from `["*"]` to `["GET","POST","PUT","PATCH",
  "DELETE","OPTIONS"]` and `["Authorization","Content-Type"]`.
- **Share-slug disclosure to viewers is fixed.**
  `GET /api/runs/{id}/share` previously returned the active slug to
  any authenticated user, so a viewer could enumerate and
  redistribute every active public URL. The endpoint now returns
  `{"is_shared": bool}` to viewers and the full
  `{"share_slug", "is_shared"}` only to operator+admin. Saved
  comparisons list/get apply the same filter: `share_slug` in the
  response body is masked to `null` for viewers; the new
  `is_shared` boolean is always present.
- **SSO config writes are now optimistically versioned.**
  `PUT /api/auth/sso/config` accepts an `expected_version` field;
  `GET` returns `version` (ISO timestamp of the current row). If an
  admin PUTs with a stale `expected_version`, the endpoint returns
  409 Conflict instead of silently clobbering a concurrent edit. A
  sentinel-based contract in `save_sso_config()` distinguishes
  "omitted → force save (tooling only)" from "None → expects no row
  yet" from "string → expects this exact version". The Sso admin
  page automatically forwards the loaded `version` as
  `expected_version` on save.

### Tests
- 3 new tests (89 total) covering: viewer cannot see share_slug in
  `/api/runs/{id}/share`; SSO config 409 on stale version; SSO
  config first-write without version is accepted.

## 0.16.0 — 2026-04-23

### Added
- **End-to-end API integration tests.** New test infrastructure spins
  up the real FastAPI app against an in-memory aiosqlite engine per
  test (via a StaticPool) and drives it through httpx + ASGITransport
  so every test exercises real routing, auth, and ORM paths without
  needing a live Postgres:
  - **RBAC enforcement (`test_rbac_e2e.py`, 9 tests)**: viewer cannot
    POST `/api/runs` (403), operator cannot `GET /api/admin/users`
    (403), admin can, viewer can list runs, missing token → 401,
    invalid token → 403, wrong password → 401, unknown user → 401,
    disabled user → 401.
  - **SSO / share / env-tune contract (`test_api_integration.py`,
    8 tests)**: SSO assertion endpoint rejects unauth callers with
    401 and viewer tokens with 403; responds 403 with a clear
    `SSO is not enabled` message when SSO is off; share create →
    public GET → revoke → public GET returns 404; public share
    redacts the device serial (full serial not in HTML body, last 4
    chars still visible); nonexistent slugs return 404; env-tune
    revert with unknown `receipt_id` returns 404; missing body is
    a 422.
  - **Startup reconciliation (`test_reconcile.py`, 4 tests)**: stale
    `preflight`/`running` rows are marked `failed` with the "API
    restarted" reason; `queued` rows are re-enqueued; `complete`
    rows are untouched; the function is idempotent across repeated
    calls.

### Changed
- SQLAlchemy `JSONB` column type now uses a `with_variant(JSON(),
  "sqlite")` wrapper so tests can run against aiosqlite while
  production deployments keep native Postgres JSONB semantics
  (indexing, operators, etc.).
- `AuditLog.id` likewise uses `BigInteger().with_variant(Integer(),
  "sqlite")` so autoincrement works under SQLite (which only
  autoincrements INTEGER PKs, not BIGINT).

### Notes
- Tests now cover every Oracle audit finding from the 1.0.0
  pre-release security pass: RBAC (finding 8), SSO endpoint gate
  (finding 1), share revoke behavior (finding 7 baseline), env-tune
  receipt handling (finding 3), and startup reconciliation (finding
  5). Runner terminal-event coverage was added in 0.15.0.
- Total backend test count: **83** (was 62).

## 0.15.0 — 2026-04-23

### Fixed
- **Runner disconnect no longer records a crashed run as `complete`.**
  `RunnerClient.run_benchmark()` previously returned silently on EOF
  or read-timeout, so a truncated stream let `_execute_run()` fall
  straight into the smart-after / `RunStatus.COMPLETE` path — silent
  result corruption. The stream now tracks whether it observed a
  terminal event (`run_complete`, `run_failed`, or `run_aborted`) and
  raises a new `RunnerStreamTruncated` exception if it did not. The
  orchestrator's worker catches that exception and marks the run
  `failed` with an explicit reason. A 3600 s read timeout also raises
  instead of silently breaking out of the loop. Five new tests cover
  the terminal-event contract (each of the three terminal kinds
  accepted; missing-terminal and immediate-EOF both raise).
- **Worker loop survives Postgres outages mid-run.** The except
  branches in `JobQueue._run_forever()` previously called
  `_mark_failed()` / `_mark_aborted()` directly, so a database error
  during failure-marking propagated out of the worker task and the
  entire queue stopped scheduling. Wrapped both calls in
  `_safe_mark_failed()` / `_safe_mark_aborted()` that log the
  persistence error but never raise, so a transient DB outage leaves
  the worker loop intact to resume work when the DB returns. The
  queue-get loop also catches and retries non-cancel exceptions with
  a 1 s backoff.
- **Defense-in-depth: `_execute_run()` refuses to mark a run
  `complete` without having observed a `run_complete` event.** Even
  if a future refactor breaks the stream-truncation guard, the
  orchestrator now independently tracks `saw_complete` across the
  event loop and raises if the generator exits cleanly without the
  expected terminal event.

### Added
- **Startup reconciliation of in-flight runs.** New
  `reconcile_on_startup()` runs in the FastAPI lifespan before the
  queue worker takes its first job:
  - `queued` rows are re-enqueued so an API restart between the
    `INSERT` and the in-memory `asyncio.Queue.put()` no longer
    strands a run forever.
  - `preflight` / `running` rows are marked `failed` with the message
    "API restarted while this run was in progress; partial state is
    unrecoverable. Re-queue the run to try again." because the fio
    process inside the runner container is gone and mid-phase state
    cannot be recovered safely.
  - Idempotent; safe to call more than once; failures during
    reconciliation are logged but do not block startup.

## 0.14.0 — 2026-04-23

### Security
- **SSO assertion endpoint is now admin-gated.** Previously
  `POST /api/auth/sso/assertion` trusted caller-supplied `username` and
  `groups` behind only the SSO-enabled flag, which meant once SSO was
  turned on any caller on the LAN could mint a JWT for any username and
  escalate to admin via group mapping. The endpoint is now explicitly
  an admin-only provisioning smoke test; it is not a login path. A
  real ACS that validates signature, issuer, NotOnOrAfter, audience,
  and replay must still be built before SSO can be a production login
  flow. Docstrings on the handler and on `SsoAssertionRequest`
  document the trust boundary so the `require_admin` gate does not get
  removed by a future refactor.
- **env-tune revert no longer trusts client-supplied paths.** Apply
  now persists the receipt server-side in the new `tune_receipts`
  table and returns a `receipt_id`; revert takes only `{receipt_id}`
  and loads the stored `results` list from the database, so a
  malicious admin request cannot redirect the privileged sysfs write
  to arbitrary paths. The runner additionally enforces an explicit
  sysfs-glob allowlist inside `_write_sysfs()` — any write that falls
  outside the known tunable globs is rejected with `PermissionError`
  (defense-in-depth; previously the allowlist was only checked in
  `apply()`). Attempts to use `..` traversal or to point at
  `/etc/passwd` / `/proc/sysrq-trigger` are refused.
- **Stored XSS in HTML reports is fixed.** Every interpolated string
  in `anvil.reports.render_run_html()` (profile name, device model,
  firmware, vendor, PCIe metadata, phase name/pattern, SVG legends and
  axes, comparison name/description) now flows through
  `html.escape(..., quote=True)` via the new `_e()` helper. A hostile
  device model or comparison name cannot execute script on the public
  `/r/runs/{slug}` or `/r/compare/{slug}` pages any more. Four
  regression tests cover the escape paths for profile, device, phase,
  and the redacted code path.
- **Strict Content-Security-Policy on every report response.**
  Public share endpoints and the authenticated HTML export now set
  `Content-Security-Policy: default-src 'none'; style-src
  'unsafe-inline'; img-src data:; font-src data:; frame-ancestors
  'none'; base-uri 'none'; form-action 'none'`, plus
  `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`
  on public responses. Because the exports are self-contained (no
  external scripts, images, fonts, or forms) a strict CSP costs
  nothing and hard-stops any future XSS vector if an escape is missed.

### Changed
- `_bootstrap_admin()` is now idempotent against a pre-existing `admin`
  user. If a disabled or non-admin user named `admin` already exists,
  startup promotes that row (active=true, role=admin, password reset
  to the bearer-token bootstrap value) instead of blindly inserting
  and hitting the unique-constraint on `users.username`.
- Frontend vite build now splits vendor bundles
  (echarts / react / query / i18n / router) so the entrypoint chunk is
  under 110 KB gzipped instead of 465 KB. ECharts remains its own
  ~350 KB gzipped lazy-loadable chunk. Chunk-size warning threshold
  raised to 1200 KB so a regression still fires.

### API
- `POST /api/environment/tune/apply` response now includes
  `receipt_id` (a ULID). Old callers that read `.results` still work.
- `POST /api/environment/tune/revert` now accepts `{receipt_id}`
  instead of `{results}`. A second revert of the same receipt
  returns 409 Conflict. A missing receipt returns 404.

### Migrations
- **`20260423_0005_tune_receipts`** — new `tune_receipts` table
  (`id`, `results` JSONB, `reverted`, `created_at`, `created_by` FK
  to users with ON DELETE SET NULL).

## 0.13.0 — 2026-04-23

### Added
- **Public share links for runs**. Operators and admins can generate a
  revocable, redacted-serial public URL for any run via the Share
  button on the Run Detail page:
  - `POST /api/runs/{id}/share` generates (or rotates) a 128-bit
    url-safe slug.
  - `DELETE /api/runs/{id}/share` revokes the slug — the URL stops
    working immediately.
  - `GET /api/runs/{id}/share` reports the current slug (viewer-readable).
  - `GET /r/runs/{slug}` serves an unauthenticated HTML report
    identical to the private HTML export but with the device serial
    masked (last 4 chars visible). Responses carry `X-Robots-Tag:
    noindex` to keep shared runs out of search engines.
- **Saved comparisons** with shareable links. New `saved_comparisons`
  table lets operators name a selection of runs and revisit / share it:
  - `GET  /api/comparisons` — list all saved comparisons.
  - `POST /api/comparisons` — create (operator+admin).
  - `GET  /api/comparisons/{id}` — fetch one.
  - `PUT  /api/comparisons/{id}` — update (operator+admin).
  - `DELETE /api/comparisons/{id}` — delete (operator+admin).
  - `POST /api/comparisons/{id}/share` / `DELETE .../share` —
    generate or revoke the public slug.
  - `GET /r/compare/{slug}` — public, serial-redacted multi-run
    report that stitches together one redacted run section per run ID.
- **Slug helpers** in the new `anvil.shares` module: 128-bit
  `secrets.token_urlsafe(16)` slugs with a unique index per column to
  guarantee no collisions at scale.
- **Nginx routing** for the new public path: `/r/` is proxied to the
  API service with standard forwarded headers and a 60s read timeout
  (no long-poll semantics needed; reports are one-shot).

### Changed
- `render_run_html()` now takes a `redact: bool = False` parameter.
  When true, device serials are masked via `_redact_serial()` (all but
  last 4 characters replaced with bullets); the public share endpoint
  always renders with `redact=True`.

### Migrations
- **`20260423_0004_share_slugs`** — adds `runs.share_slug`
  (nullable, unique index) and creates the `saved_comparisons` table
  with its own `share_slug` unique index and a nullable
  `created_by` FK to `users.id` with `ON DELETE SET NULL`.

### Notes
- Share slugs are opaque random tokens, not sequential IDs; an attacker
  cannot enumerate shared runs. Revocation is immediate (the slug is
  nulled; the URL 404s on the next request).
- A shared run's chart axes, phase table, and time-series data are
  included verbatim — only the device serial is redacted. If you
  consider model name or firmware sensitive, do not share publicly.

## 0.12.1 — 2026-04-23

### Fixed
- **Admin bootstrap crash on multi-admin deployments**. The startup
  `_bootstrap_admin()` used `scalar_one_or_none()` to check whether any
  admin user already exists, which raised `MultipleResultsFound` and
  crash-looped the API container on live deployments that already had
  more than one active admin (e.g. the bootstrap `admin` row plus one
  SSO-provisioned admin). Switched to a `SELECT COUNT(*) > 0` check so
  the presence of any admins short-circuits the bootstrap regardless
  of how many exist.

## 0.12.0 — 2026-04-23

### Added
- **Run report exports**. Every completed run can now be exported as a
  self-contained, zero-JavaScript HTML document or a lossless JSON
  bundle:
  - `GET /api/runs/{id}/export.html` returns a printable HTML report
    with embedded CSS, server-side SVG line charts (IOPS / bandwidth /
    latency / temperature over time), the full phase table, SMART
    before/after diffs, the PCIe link card (capability vs. runtime
    state with degraded-link warning), host environment snapshot, and
    SNIA steady-state analysis where applicable. Suitable for
    archival, email attachment, or print-to-PDF.
  - `GET /api/runs/{id}/export.json` returns a complete JSON archive
    containing the run record, all phases, per-phase fio samples, the
    captured SMART before/after snapshots, the PCIe snapshot at run
    time, the device metadata, and the SNIA analysis output (when
    eligible) — a machine-readable sibling of the HTML report.
- **"Export HTML" and "Export JSON" buttons** on the Run Detail page
  topbar (with zh/en i18n) that open the report directly in a new
  tab, passing the session token via `?token=…` query parameter so
  anchor-based GET downloads work without custom fetch plumbing.

### Changed
- `resolve_principal()` now accepts the session token via an optional
  `?token=…` query parameter in addition to the `Authorization:
  Bearer …` header. Header auth remains preferred for API callers;
  the query form exists specifically to enable browser-initiated GET
  downloads (anchor tags, `window.open`, file-save prompts) that
  cannot set custom headers.

### Notes
- The HTML export renders SVG charts server-side with hand-rolled path
  math (no JS runtime dependency, no external chart libs), so the
  exported file displays identically across browsers and survives
  print-to-PDF conversion.
- The JSON bundle includes every raw fio sample point, which can be
  large (hundreds of KB) for long-running endurance soaks; the HTML
  export downsamples the time series to ~400 points per metric for
  readability while keeping peaks visible.

## 0.11.0 — 2026-04-22

### Added
- **Admin-configurable SSO integration points**. New module
  `anvil.sso` defines an IdP-agnostic policy layer: an `SsoConfig`
  dataclass (enabled flag, IdP metadata URL, entity IDs, attribute
  name overrides, default role, and a group→role mapping list) plus
  `resolve_sso_role()` which takes the groups asserted by the IdP and
  returns the highest matching Anvil role (admin > operator > viewer)
  or the config's default role when nothing matches.
- **`app_settings` table** via Alembic migration `20260422_0003`, for
  JSONB config entries keyed by string. SSO config lives under key
  `sso`; future app-level config can share the table.
- **`provision_sso_user()`** upserts a User row for an SSO-authenticated
  username, syncs the role from the current mapping on every login
  (so role revocations propagate without manual cleanup), and never
  sets a password hash — SSO-only users can't sign in via the
  username+password form.
- **New admin API endpoints**:
  - `GET /api/auth/sso/config` — fetch current settings.
  - `PUT /api/auth/sso/config` — save settings (validates every role
    name against the UserRole enum).
  - `POST /api/auth/sso/assertion` — consume a pre-validated assertion
    (username + display_name + groups), provision the user, issue a
    JWT. Guarded by the `enabled` flag: 403 if SSO is off. Crypto
    validation is explicitly out of scope for this endpoint — it's
    the hook point for a real SAML library integration, not a
    self-contained IdP.
- **`/admin/sso` page** (admin nav entry): form for every config field,
  a group→role mapping editor (add/remove/reorder/edit rows), save
  button with server-side validation surfacing, plus a "test
  assertion" smoke-test panel so admins can verify their mapping
  resolves to the expected role before connecting a real IdP.

### Why this shape
SAML parsing libraries (`python3-saml`, `pysaml2`) change APIs across
versions and cover overlapping but distinct feature sets (AD FS vs
Azure AD vs Okta vs Keycloak). The user asked to "reserve the SSO
capability with interactive admin config", so this release ships the
parts Anvil controls (storage, policy, admin UI) with a clean
integration point for the IdP-specific crypto library. When a concrete
library is chosen, only the `/auth/sso/assertion` handler is edited —
`provision_sso_user()` and the mapping logic stay unchanged.

## 0.10.0 — 2026-04-22

### Added
- **One-click environment auto-tune (admin-only)**. New runner module
  `anvil_runner/env_tune.py` writes an explicit allow-list of host
  sysfs paths via `/proc/1/root/sys/...`:
  - `cpu_governor` → `performance` (all cores)
  - `pcie_aspm_policy` → `performance`
  - `nvme_scheduler` → `none` (all NVMe namespaces)
  - `nvme_nr_requests` → `2048`
  - `nvme_read_ahead_kb` → `128`
  Every tunable has a human-readable description baked into the module
  so the UI can render the preview table without any frontend-side
  lookup table.
- **Transactional apply**. The `apply()` function records a per-path
  before/after receipt. If any write raises `OSError`, every previously-
  successful write in the batch is reverted automatically in reverse
  order. The receipt is returned to the caller so they can pass it back
  to `revert()` later for a deterministic undo.
- **New backend endpoints** under `/api/environment/tune/`:
  - `GET /preview` — dry-run: which paths would change to which values.
  - `POST /apply` — admin-only, returns the receipt + audits to
    `audit_log`.
  - `POST /revert` — admin-only, replays `before` values from a prior
    receipt.
- **New runner RPC methods**: `tune_preview`, `tune_apply`,
  `tune_revert` over the existing UDS JSON-RPC channel.
- **System page Auto-tune card** (admin-only). Shows a preview table
  of every tunable path with current vs desired and a "will change" /
  "already ok" badge. Apply and Revert buttons. After apply, the
  receipt renders with before / after / ok for every path, including
  any revert_error from a partial rollback.

### Changed
- `/system` now refetches its environment report automatically after
  a successful apply / revert so you can see the checks flip from
  warn → pass without reloading.

## 0.9.0 — 2026-04-22

### Added
- **RBAC with three roles** (Viewer / Operator / Administrator).
  - `users` table added via Alembic migration `20260422_0002`. Rows
    carry username, bcrypt password hash, role, active flag,
    last-login timestamp, and metadata JSONB.
  - New module `anvil.auth` with bcrypt password hashing, short-lived
    (12 h) HS256 JWT issuance, and `require_viewer` /
    `require_operator` / `require_admin` dependency factories.
  - Legacy `ANVIL_BEARER_TOKEN` continues to work as a synthetic
    "operator-token" principal with admin role so every existing CI
    integration test and curl script keeps functioning unchanged.
- **New API endpoints**:
  - `POST /api/auth/login` (username + password → JWT).
  - `GET /api/auth/me` (introspection).
  - `GET /api/admin/users`, `POST /api/admin/users`,
    `PATCH /api/admin/users/{id}`, `DELETE /api/admin/users/{id}` for
    administrator-only user CRUD.
- **Endpoint role enforcement**:
  - `POST /api/runs`, `POST /api/runs/{id}/abort`, and
    `POST /api/devices/rescan` now require the Operator role.
  - All admin user-management endpoints require Administrator.
  - Everything else is Viewer (any authenticated caller).
- **Bootstrap admin**. On first startup with no admin user present, a
  `admin` user is auto-created with a password equal to the first 16
  characters of `ANVIL_BEARER_TOKEN`. A warning is logged; operators
  should rotate the password immediately from the new Users page.
- **Login form on the auth gate**. Two tabs — username+password and
  legacy bearer-token — so both humans and automation can authenticate.
  The sidebar now shows the signed-in username plus a role-coloured
  badge (admin red, operator yellow, viewer default).
- **Users admin page (`/admin/users`)** visible in the sidebar only
  to admins (and the legacy token principal). Supports creating,
  role-changing, deactivating, and deleting users; audit log records
  every operation.

### Notes
- Existing SSO / SAML integration is prepared for but not yet wired;
  that's the next cycle.

## 0.8.0 — 2026-04-22

### Added
- **Redesigned dashboard** with 8 panels across two levels of storytelling:
  operator (what's going wrong right now) + external-visitor (what the
  lab has done). New panels:
  - **KPI strip** (6 cards): testable drives / fleet size, brands seen,
    total runs with ok/fail/aborted breakdown, cumulative approximate
    bytes-written (Σ write BW × runtime), runner connection status with
    coloured dot, environment health status with click-through to
    `/system`.
  - **PCIe-degraded drives alert** (highlighted yellow): any testable
    device whose `LnkSta < LnkCap`. Direct link to the device detail
    page for forensics.
  - **Recent alarms** (highlighted red): runs that failed or were aborted
    in the last 24 hours, with the `error_message` column so operators
    can spot thermal-abort reasons at a glance.
  - **30-day activity timeline**: stacked-bar chart of complete / failed /
    aborted runs per day.
  - **4 leaderboards**: top-5 by 4 K QD1 random read IOPS, top-5 by
    4 K QD32 random read IOPS, top-5 by 1 MiB QD8 sequential read BW,
    top-5 by 4 K QD32 random read p99 latency (lowest is best). Every
    entry links both to the device detail page and the specific run.
  - **Recent runs** (kept and polished): last 10 runs with click-through
    to both run and device pages.

### Added (backend)
- New `/api/dashboard/*` endpoints powering the above: `fleet-stats`,
  `leaderboards?limit=N`, `pcie-degraded`, `activity?days=N`,
  `alarms?hours=N`. All are cheap aggregations; the dashboard page
  parallelises them via TanStack Query.

## 0.7.1 — 2026-04-22

### Fixed
- **PCIe probe silently returned None for every NVMe device.** The
  controller-name extraction used `kname.split("n", 1)[0]`, which on
  `nvme1n1` splits on the FIRST `n` and returns an empty string. The
  Python probe still worked when called directly with `"nvme0"`, but
  discovery's call-site got `""` → `lspci` had no address to query → no
  pcie data ever reached the Device row. Replaced with
  `re.match(r"^(nvme\\d+)", kname)` which correctly handles
  `nvme0n1` → `nvme0`, `nvme12n3` → `nvme12`, and multipath
  `nvme0c0n1` → `nvme0`.

## 0.7.0 — 2026-04-22

### Added
- **PCIe link capability + current state recorded for every NVMe
  device**, fulfilling the "device supports PCIe 5.0 x4 but this test
  ran at PCIe 4.0 x4" requirement. New `anvil_runner/pcie.py` module
  reads `/sys/class/nvme/<n>/address` for each NVMe controller, runs
  `lspci -vvv -s <bdf>` in the host namespace, and parses the `LnkCap`
  and `LnkSta` lines into a structured
  `{capability, status, degraded, speed_degraded, width_degraded}`
  object.
- PCIe probe output is persisted in three places:
  - `Device.metadata_json.pcie` — always reflects the latest rescan
  - `DeviceSnapshot.pcie` — historical record per rescan
  - `Run.host_system.pcie_at_run` — snapshot taken at the moment the
    run started, so the report shows the exact link state that was in
    effect when the benchmark collected its numbers (immune to later
    hot-swaps / re-insertions)
- New `PcieLinkCard` component auto-renders on:
  - Run detail page, underneath the SMART diff, so every report shows
    the link state that was actually active while fio was running
  - Device detail page, so even before a run the user can see how the
    drive is currently connected
  The card shows a green "optimal" badge when `LnkSta == LnkCap` and a
  yellow "degraded" badge otherwise, with sub-badges for
  speed-downgraded and width-downgraded so the reader can tell
  immediately which dimension is mis-matched. The raw `lspci` lines
  are shown in a dim monospace column for operator forensics.

### Changed
- `GET /api/devices/{id}/history` now also returns `pcie` so the
  device detail page renders the card with one fetch.

## 0.6.0 — 2026-04-22

### Added
- **`endurance_soak` profile**. 2-hour sustained 4 KiB random write at
  QD 32 with 8 jobs, preceded by a 60 s sequential-write
  preconditioning pass. Preset for long-duration wear / thermal
  behavior characterization.
- **Thermal auto-abort**. The existing SMART-temperature poller now
  tracks a consecutive-overheat counter during every run. If the drive
  sustains ≥ 75 °C for 6 consecutive samples (≈ 30 s at the 5 s poll
  interval) the runner cancels the currently-executing phase and emits
  a `run_aborted` event with `reason: "thermal_abort"`. The
  orchestrator surfaces this in the run's `error_message` column as
  `thermal_abort: temperature ≥ 75 °C for 6 consecutive SMART samples`
  so it's obvious why the run stopped. Applies to every profile, not
  just endurance — a Quick run that overheats will still be aborted
  safely.
- New RPC event `thermal_abort_armed` broadcast to the WebSocket the
  moment the threshold is breached (before the actual phase cancel
  completes), so the UI can surface a red banner immediately.

### Implementation notes
- The phase loop in `_run_benchmark_stream` now runs each phase's
  event-drain inside its own `asyncio.Task`. That task is cancelled
  by the thermal watcher if the abort event fires; a `CancelledError`
  is caught and translated to a graceful `run_aborted` emission, not
  re-raised. This also lays the groundwork for per-phase user abort
  (where the orchestrator can cancel a specific task rather than the
  whole runner connection).

## 0.5.0 — 2026-04-22

### Added
- **SNIA SSS PTS v2.0.2 steady-state analysis**. New module
  `backend/anvil/profiles/snia.py` implements `evaluate_steady_state()`:
  takes the last 5 round observations of the canonical 4 KiB 100 %
  write IOPS metric and applies the spec's two simultaneous
  criteria — `range ≤ 20 % × mean` and `|slope| × window_span ≤ 10 %
  × mean`. Pure math, 8 pytest cases covering flat / range-violation /
  slope-violation / sliding-window / degenerate / custom-threshold
  paths. Spec references baked into the module docstring so tolerances
  can't silently drift.
- **`snia_quick_pts` benchmark profile**. 5 rounds × (3 block sizes ×
  3 R/W mixes) = 45 cells at 45 s each plus a 60 s sequential-write
  preconditioning pass. ~35 min total, destructive. Cells are named
  `snia_r<round>_bs<bs>_w<writePct>` so the analysis endpoint can
  parse the round structure back out deterministically.
- **`GET /api/runs/{id}/snia-analysis`**. Groups a run's completed
  phases by round, extracts the canonical metric, runs
  `evaluate_steady_state`, and returns both the full round-by-round
  matrix and the steady-state verdict (steady flag, range/slope
  diagnostics, reason code).
- **SNIA analysis card on Run detail**. Auto-renders whenever the run
  profile name starts with `snia_`. Shows the canonical IOPS metric
  as a line chart across rounds with ±20 % tolerance band, a verdict
  badge (steady / range_exceeded / slope_exceeded / warming_up), and
  a criteria table with observed vs limit values per criterion.

### Notes
- This cycle ships a fully-static 5-round SNIA profile, not the
  adaptive run-rounds-until-convergence loop described in the design
  doc. Adaptive SNIA requires rewriting the orchestrator's phase
  iteration to consume tracker output mid-run; that work belongs in a
  follow-up cycle. The math core shipped here is reusable for that
  future adaptive runner — it's deliberately isolated from any I/O.

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
