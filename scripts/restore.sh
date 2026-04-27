#!/usr/bin/env bash
# Restore an Anvil backup tarball (created by backup.sh).
# This stops the service, restores the database, and restarts.
#
# Usage:   ./scripts/restore.sh <tarball>
#
# WARNING: This will overwrite the current database. Have a fresh
#          backup before restoring.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <tarball>" >&2
  exit 1
fi

TARBALL="$1"
if [ ! -f "$TARBALL" ]; then
  echo "ERROR: $TARBALL not found" >&2
  exit 1
fi

echo "This will STOP the Anvil service and RESTORE the database from:"
echo "  $TARBALL"
echo
read -r -p "Are you sure? (y/N) " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
  echo "aborted"
  exit 0
fi

TMPDIR="$(mktemp -d -t anvil-restore.XXXXXX)"
trap 'rm -rf "$TMPDIR"' EXIT

echo "=== extracting backup ==="
tar -xzf "$TARBALL" -C "$TMPDIR"
BACKUP_DIR="$(echo "$TMPDIR"/anvil-*)"

if [ ! -f "$BACKUP_DIR/db/anvil.sql" ]; then
  echo "ERROR: no db/anvil.sql found in backup" >&2
  exit 1
fi

echo "=== stopping service ==="
cd "$REPO_DIR"
docker compose down

echo "=== restoring database ==="
docker compose up -d db
sleep 3

docker compose exec -T db psql -U anvil -d anvil \
  < "$BACKUP_DIR/db/anvil.sql" 2>&1 | tail -5

echo "=== starting service ==="
docker compose up -d

echo "=== waiting for API health ==="
for i in $(seq 1 30); do
  if curl -sf http://localhost:8080/api/health > /dev/null 2>&1; then
    echo "✓ healthy after ${i}s"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "WARNING: API did not become healthy within 30s" >&2
  fi
  sleep 1
done

echo "✓ restore complete"
echo "   Stack is running. Verify at http://localhost:8081"
