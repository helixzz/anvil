#!/usr/bin/env bash
# Backup Anvil's PostgreSQL database and configuration files into a
# timestamped tarball. Safe to run while the stack is online (pg_dump is
# consistent regardless of ongoing writes).
#
# Usage:   ./scripts/backup.sh [output-dir]
# Default: ./anvil-backups/
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${1:-$REPO_DIR/anvil-backups}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMPDIR="$(mktemp -d -t anvil-backup.XXXXXX)"
trap 'rm -rf "$TMPDIR"' EXIT

STAGEDIR="$TMPDIR/anvil-$TIMESTAMP"
mkdir -p "$STAGEDIR/db"

echo "=== dumping PostgreSQL database ==="
cd "$REPO_DIR"
docker compose exec -T db pg_dump -U anvil -d anvil --clean --if-exists \
  > "$STAGEDIR/db/anvil.sql" 2> "$TMPDIR/pg-dump-err.log" || {
    echo "ERROR: pg_dump failed (see $TMPDIR/pg-dump-err.log)" >&2
    exit 1
}

DUMP_SIZE="$(wc -c < "$STAGEDIR/db/anvil.sql")"
echo "   SQL dump: $DUMP_SIZE bytes"

echo "=== copying config files ==="
for f in .env docker-compose.yml mkdocs.yml; do
  if [ -f "$REPO_DIR/$f" ]; then
    cp "$REPO_DIR/$f" "$STAGEDIR/$f"
  fi
done
cp -r "$REPO_DIR/deploy" "$STAGEDIR/deploy" 2>/dev/null || true

cat > "$STAGEDIR/BACKUP-INFO.txt" <<EOF
Anvil backup created on $(date -u)
Dump size:    $DUMP_SIZE bytes
Components:   database SQL + .env + docker-compose.yml + deploy/
Restore with: ./scripts/restore.sh <tarball>
EOF

TARBALL="$BACKUP_DIR/anvil-$TIMESTAMP.tar.gz"
echo "=== creating tarball ==="
tar -czf "$TARBALL" -C "$TMPDIR" "anvil-$TIMESTAMP"
TAR_SIZE="$(du -h "$TARBALL" | cut -f1)"
echo "   $TARBALL ($TAR_SIZE)"

echo "✓ backup complete"
