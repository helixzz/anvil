# Public share links

Anvil can expose any completed run or any saved multi-run comparison
as a **public URL** — no login required — with the device serial
redacted.

## Share a run

On the Run Detail topbar, operator+admin users see:

1. **Create share link** — generates a 128-bit opaque slug and
   returns the full public URL
2. **Copy link** — clipboard-copies the URL (falls back to a prompt
   on non-HTTPS browsers)
3. **Revoke** — nulls the slug; the URL 404s on next request

A shared run renders the same HTML as the authenticated export, with
these differences:

- Device serial is masked to `••••••last4`
- Response carries `X-Robots-Tag: noindex` (search engines skip it)
- Strict `Content-Security-Policy` — no scripts, no remote images
- `Cache-Control: public, max-age=300` for a short CDN-friendly
  window

What is **NOT** redacted:
- Model, firmware, vendor, capacity, PCIe state, host kernel, SMART
  values, all metrics

If you consider those sensitive, do not share publicly.

## Share a saved comparison

Saved comparisons live under `/api/comparisons`:

```bash
# Create (operator+admin)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Gen5 drives Q2 2026",
       "description": "Release candidates for the next procurement cycle",
       "run_ids": ["01K...", "01K..."]}' \
  http://localhost:8080/api/comparisons

# Share it (operator+admin)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/comparisons/{id}/share
# -> {"id": "...", "share_slug": "Ab7x..."}

# Public view (no auth)
curl http://localhost:8080/r/compare/Ab7x...
```

The public page stitches together one redacted run report per
`run_id` in the comparison.

## Slug security

- Slugs are 128 bits of `secrets.token_urlsafe(16)` entropy —
  enumeration is infeasible
- Only operator+admin can read the active slug via the API; viewers
  see only an `is_shared: bool` flag so they can't pass around active
  URLs without being granted the right
- Revocation is immediate; the URL 404s on the next request
- Slugs **do not** rotate on POST — the same slug is returned if one
  already exists. To rotate, DELETE then POST again.
