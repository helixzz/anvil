# Security notes

Anvil is designed for a **single-tenant, trusted-LAN** deployment.
Several design decisions make sense in that context and would be
indefensible on a public-Internet service. This page documents them
so an operator can make an informed decision.

## Trust model

- The LAN is trusted; TLS is not built in. Terminate HTTPS at an
  upstream proxy if you need encryption in transit.
- The privileged runner container has `--privileged`, `pid=host`,
  and bind-mounts to `/dev`, `/sys`, `/proc`. Anyone with admin
  credentials can send it `fio`, `nvme`, or env-tune commands.
- The database holds raw SMART snapshots, device serials, and bcrypt
  password hashes. Back it up like any credential store.

## Public share links

- Slugs are 128-bit opaque tokens; enumeration is infeasible.
- Only operator+admin can read the active slug. Viewers see only
  a boolean.
- Serial is redacted on public reports; **everything else is not**.
  If you consider model, firmware, or vendor sensitive, do not
  share publicly.
- Responses carry strict CSP + `nosniff` + `no-referrer` +
  `noindex` headers.

## SSO assertion endpoint

`POST /api/auth/sso/assertion` trusts its input (caller-supplied
`username`, `groups`). It is hard-gated behind `require_admin` and
should **not** be used as a login primitive. Removing the
`require_admin` dep turns it into an auth bypass. A production SAML
ACS that validates signature, issuer, audience, and replay is out
of scope for 1.0.0.

## Env-tune allowlist

The runner refuses any privileged sysfs write outside a hardcoded
glob allowlist. Apply receipts are persisted server-side; revert
takes only a receipt ID and reuses the server-side path list. A
malicious admin request cannot supply an arbitrary path.

## CORS

Default origins list is **empty** — no CORS middleware is installed
unless an operator lists origins explicitly. Wildcard + credentials
is forced to `credentials=false` with a warning, because the browser
refuses the combination anyway.

## XSS

Every interpolated value in the HTML report (profile name, device
model, firmware, vendor, phase name, comparison name, SVG legend
labels) flows through `html.escape(..., quote=True)`. Strict CSP is
the second line of defense.

## Bearer token rotation

Rotating `ANVIL_BEARER_TOKEN` does three things at once:

1. Invalidates every JWT (signing secret changed)
2. Changes the legacy static admin credential
3. Resets the bootstrap admin password (for any future first-boot)

Rotate only during a maintenance window, and be prepared to log in
with the **new** bootstrap password if you do it on a fresh install.

## Audit log

Every privileged action writes an `audit_log` row with
`actor`, `action`, `target`, and JSON `details`. Query from psql:

```sql
SELECT ts, actor, action, target, details
FROM audit_log
ORDER BY ts DESC
LIMIT 50;
```

There's no UI for the audit log yet; this is on the post-1.0
roadmap.
