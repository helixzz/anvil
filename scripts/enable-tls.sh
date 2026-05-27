#!/usr/bin/env bash
# Enable HTTPS for Anvil by configuring TLS certificates.
#
# Usage:
#   ./scripts/enable-tls.sh <cert.pem> <key.pem> [ca-bundle.pem]
#
# This script:
#   1. Copies your certificate + key into deploy/tls/
#   2. Switches nginx to the TLS config (frontend/nginx-tls.conf)
#   3. Updates docker-compose.yml to mount the TLS volume + expose port 443
#   4. Restarts the web container
#
# After running, Anvil will be reachable at https://<host>:8443
# HTTP on port 8081 will redirect to HTTPS.
#
# To revert: remove deploy/tls/ and rebuild with the original nginx.conf.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 2 ]; then
  echo "Usage: $0 <cert.pem> <key.pem> [ca-bundle.pem]" >&2
  echo "" >&2
  echo "  cert.pem     - Server certificate (PEM, from your enterprise CA)" >&2
  echo "  key.pem      - Private key (PEM, unencrypted)" >&2
  echo "  ca-bundle.pem - Optional CA chain bundle" >&2
  exit 1
fi

CERT="$1"
KEY="$2"
CA_BUNDLE="${3:-}"

if [ ! -f "$CERT" ]; then echo "ERROR: $CERT not found" >&2; exit 1; fi
if [ ! -f "$KEY" ]; then echo "ERROR: $KEY not found" >&2; exit 1; fi

TLS_DIR="$REPO_DIR/deploy/tls"
mkdir -p "$TLS_DIR"

echo "=== copying certificates ==="
cp "$CERT" "$TLS_DIR/tls.crt"
cp "$KEY" "$TLS_DIR/tls.key"
chmod 600 "$TLS_DIR/tls.key"
if [ -n "$CA_BUNDLE" ] && [ -f "$CA_BUNDLE" ]; then
  cp "$CA_BUNDLE" "$TLS_DIR/ca-bundle.crt"
  echo "   CA bundle: $CA_BUNDLE → deploy/tls/ca-bundle.crt"
fi
echo "   cert: $CERT → deploy/tls/tls.crt"
echo "   key:  $KEY → deploy/tls/tls.key"

echo "=== switching to TLS nginx config ==="
cp "$REPO_DIR/frontend/nginx.conf" "$REPO_DIR/frontend/nginx.conf.bak"
cp "$REPO_DIR/frontend/nginx-tls.conf" "$REPO_DIR/frontend/nginx.conf"

echo "=== rebuilding web container ==="
cd "$REPO_DIR"
docker compose build web
docker compose up -d web

echo ""
echo "✓ TLS enabled."
echo "  HTTPS: https://$(hostname):8443"
echo "  HTTP redirect: http://$(hostname):8081 → https"
echo ""
echo "  To update certificates later, replace deploy/tls/tls.{crt,key}"
echo "  and run: docker compose restart web"
