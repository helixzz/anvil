# ADFS Integration Guide

This guide explains how to connect Anvil to an enterprise AD FS
(Active Directory Federation Services) instance for SSO login.

## Architecture

```
Browser → Anvil frontend → /api/auth/sso/login → redirect to ADFS
ADFS authenticates user → POST SAML response → /api/auth/sso/acs
Anvil validates signature → provisions user as viewer → issues JWT → redirect to frontend
```

## Prerequisites

- AD FS 2016+ or Azure AD with SAML 2.0 support
- Anvil must be reachable via HTTPS for ADFS (ADFS typically requires HTTPS ACS URL)
- TLS certificate from enterprise CA (see `scripts/enable-tls.sh`)

## Step 1: Enable HTTPS on Anvil

```bash
./scripts/enable-tls.sh /path/to/cert.pem /path/to/key.pem /path/to/ca-bundle.pem
```

After this, Anvil is reachable at `https://anvil.yourcompany.com:8443`.

## Step 2: Download Anvil SP Metadata

```
https://anvil.yourcompany.com:8443/api/auth/sso/metadata
```

Save this XML file — you'll upload it to ADFS.

## Step 3: Configure ADFS Relying Party Trust

1. Open AD FS Management → **Relying Party Trusts** → **Add Trust**
2. Choose **Import data from file** → upload the SP metadata XML
3. Set **Display Name**: "Anvil"
4. **Configure Claim Rules** — add these issuance transform rules:

| Rule | LDAP Attribute → SAML Claim |
|------|-----|
| Rule 1 | SAM-Account-Name → Name ID |
| Rule 2 | Display-Name → `displayName` |
| Rule 3 | E-Mail-Addresses → `mail` |
| Rule 4 | Token-Groups (Unqualified Names) → `memberOf` |

5. On the **Advanced** tab, set **Secure hash algorithm** = SHA-256

## Step 4: Configure Anvil SSO Settings

Go to **Admin → SSO** in the Anvil web UI, or use the API:

```bash
TOKEN="your-admin-bearer-token"
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  https://anvil.yourcompany.com:8443/api/auth/sso/config \
  -d '{
    "enabled": true,
    "idp_metadata_url": "https://adfs.yourcompany.com/FederationMetadata/2007-06/FederationMetadata.xml",
    "idp_entity_id": "http://adfs.yourcompany.com/adfs/services/trust",
    "sp_entity_id": "anvil",
    "sp_acs_url": "https://anvil.yourcompany.com:8443",
    "username_attribute": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
    "display_name_attribute": "displayName",
    "email_attribute": "mail",
    "groups_attribute": "http://schemas.xmlsoap.org/claims/Group",
    "default_role": "viewer",
    "mappings": []
  }'
```

### Key ADFS-specific attribute names

| Field | ADFS value |
|-------|-----------|
| `username_attribute` | `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name` |
| `groups_attribute` | `http://schemas.xmlsoap.org/claims/Group` |
| `display_name_attribute` | `displayName` |

## Step 5: Test the Flow

1. Open Anvil login page — you should see "Sign in with SSO" as the primary button
2. Click it — browser redirects to ADFS login page
3. Authenticate with your domain credentials
4. ADFS redirects back to Anvil with a SAML assertion
5. Anvil creates a user record with role = **viewer**

## Role Management

- All ADFS users get `viewer` role by default (read-only: view runs, reports, status)
- Admins can promote users to `operator` (can start runs) or `admin` via **Admin → Users**
- Role promotions persist across SSO re-logins

### Optional: Group-based Role Mapping

If you want specific AD groups to auto-grant operator/admin:

```json
{
  "mappings": [
    {"group": "CN=Anvil-Operators,OU=Groups,DC=yourcompany,DC=com", "role": "operator"},
    {"group": "CN=Anvil-Admins,OU=Groups,DC=yourcompany,DC=com", "role": "admin"}
  ]
}
```

Users matching multiple groups get the highest role (admin > operator > viewer).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "SSO is not enabled" | Set `enabled: true` in SSO config |
| ADFS "Unable to process request" | Ensure SP metadata was uploaded correctly and ACS URL matches |
| "SAML response validation failed" | Check that ADFS → Anvil clock skew is < 5 minutes |
| User gets wrong role | Check `groups_attribute` matches your ADFS claim rule output |
| Want to revoke SSO for a user | Set `is_active: false` on the user record via Admin → Users |
