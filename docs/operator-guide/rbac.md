# Role-based access control

Anvil has three roles: **viewer**, **operator**, **admin**. They form
a hierarchy: admin > operator > viewer. Every admin is also an
operator; every operator is also a viewer.

## What each role can do

| Action | viewer | operator | admin |
|---|---|---|---|
| View dashboard, devices, runs | ✅ | ✅ | ✅ |
| View Run Detail + download export | ✅ | ✅ | ✅ |
| See public-share `is_shared` flag | ✅ | ✅ | ✅ |
| See public-share active slug | ❌ | ✅ | ✅ |
| Start a run | ❌ | ✅ | ✅ |
| Abort a run | ❌ | ✅ | ✅ |
| Create / revoke share links | ❌ | ✅ | ✅ |
| Save / share comparisons | ❌ | ✅ | ✅ |
| Administer users (CRUD) | ❌ | ❌ | ✅ |
| Configure SSO | ❌ | ❌ | ✅ |
| One-click env auto-tune | ❌ | ❌ | ✅ |

## Credentials

- **Password**: bcrypt hashed, stored in `users.password_hash`.
  Anvil enforces bcrypt's 72-byte password cap by truncating at 72
  bytes on encode (pre-hash), which matches passlib's legacy behavior.
- **JWT**: HS256, signed with `ANVIL_BEARER_TOKEN`, 12-hour expiry.
  Claims: `sub=user_id`, `username`, `role`, `exp`.
- **Legacy bearer token** (`ANVIL_BEARER_TOKEN`): still a valid
  admin credential; used by automation and the bootstrap admin flow.

## Bootstrap admin

On first boot (and on a DB where no active admin exists yet), Anvil
creates or promotes a user `admin` with password = first 16 chars of
`ANVIL_BEARER_TOKEN`. Rotate this password immediately.

If an `admin` user already exists (possibly disabled from a prior
deployment), Anvil promotes that row instead of creating a duplicate.

## Why role changes force re-login

A JWT embeds the user's role at issuance time. If an admin changes
a user's role while their JWT is still valid, the next authenticated
request fails with `403 Role changed; sign in again`. This prevents
a just-demoted user from continuing to act as an operator until
their token expires.
