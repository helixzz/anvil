# SSO

Anvil 1.0.0 ships with the **policy layer** for SSO and a fully
interactive admin UI for group→role mapping, but **without a
production SAML ACS**. This means:

- You can configure the IdP metadata, SP entity ID, ACS URL, and
  group→role mapping from `/admin/sso` today.
- The `/api/auth/sso/assertion` endpoint that provisions users and
  issues JWTs is **admin-only** — it's a smoke test for the mapping
  logic, not a login primitive.
- A real AuthnResponse parser that validates signature, issuer,
  audience, NotOnOrAfter, and replay is out of scope for 1.0.0 and
  will land in a later release.

## What you can configure today

From **Admin → SSO**:

- **Enabled** flag (gates the `/auth/sso/assertion` endpoint)
- IdP metadata URL and entity ID
- SP entity ID (Anvil-side; defaults to `anvil`)
- SP ACS URL (where the IdP POSTs the AuthnResponse)
- Attribute names for username / display name / email / groups
- **Group→role mappings** (one row per rule)
- **Default role** for users with no matching group

All of this is stored as a single JSONB row under
`app_settings.sso`.

## Group→role resolution

When a user logs in via SSO (once the ACS is built), Anvil:

1. Reads the asserted groups from the
   configured `groups_attribute`
2. For each mapping rule whose `group` appears in the asserted
   groups, collects the rule's `role`
3. Returns the **highest-ranked** collected role
   (admin > operator > viewer)
4. If no rule matches, returns the configured `default_role`

## Concurrency

Concurrent admin edits to the SSO config are protected by
**optimistic locking**: `GET /api/auth/sso/config` returns a
`version` (ISO timestamp); `PUT` requires `expected_version` to
match. A stale PUT returns 409 Conflict rather than silently
clobbering another admin's changes.

## Testing the mapping

The admin UI has a **Test assertion** form that accepts a username
and a comma-separated list of groups and calls
`/api/auth/sso/assertion` (admin-only). The response shows which
role the user would be assigned and issues a JWT. Use this to
verify your mapping rules before real SSO is live.

!!! warning
    Never remove the `require_admin` dependency from
    `/api/auth/sso/assertion`. Without it, the endpoint trusts
    caller-supplied `{username, groups}` and becomes a straight
    auth bypass.
