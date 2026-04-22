"""Shareable-link slugs.

Runs and saved comparisons can expose a public, unauthenticated view by
generating an opaque URL-safe slug. Slugs are:

- 128 bits of randomness (token_urlsafe(16) -> 22 chars) so enumeration
  is infeasible,
- stored nullably on the owning row (NULL = not shared),
- uniquely indexed so they map 1:1 to a resource,
- rotatable (POST /share regenerates) and revocable (DELETE sets NULL).

The public view renders the same HTML export template with redact=True
so device serials are masked on the public page.
"""
from __future__ import annotations

import secrets


def generate_slug() -> str:
    return secrets.token_urlsafe(16)
