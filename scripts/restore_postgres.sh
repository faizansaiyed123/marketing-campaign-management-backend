#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "$0")/.." && pwd)"
COMPOSE=(docker compose --project-directory "$ROOT_DIR" -f "$ROOT_DIR/docker-compose.yml")

if [[ "$#" -ne 1 ]]; then
  echo "Usage: $0 path/to/campaigns-backup.dump" >&2
  exit 2
fi
backup_file="$(cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")"
[[ -s "$backup_file" ]] || { echo "Backup file not found or empty: $backup_file" >&2; exit 2; }

echo "Validating backup archive..."
"${COMPOSE[@]}" exec -T postgres pg_restore --list < "$backup_file" > /dev/null

current_database="$("${COMPOSE[@]}" exec -T postgres sh -ec 'printf "%s" "$POSTGRES_DB"')"
RESTORE_DATABASE="${RESTORE_DATABASE:-campaigns_restore_$(date -u +%Y%m%d%H%M%S)}"
if ! [[ "$RESTORE_DATABASE" =~ ^[a-zA-Z_][a-zA-Z0-9_]{0,62}$ ]]; then
  echo "RESTORE_DATABASE must be a valid PostgreSQL identifier (letters, numbers and underscores; 63 characters max)." >&2
  exit 2
fi
if [[ "$RESTORE_DATABASE" == "$current_database" ]]; then
  echo "Refusing to restore over the configured live database. Use a new RESTORE_DATABASE name." >&2
  exit 2
fi

echo "Creating separate restore database: $RESTORE_DATABASE"
"${COMPOSE[@]}" exec -T postgres sh -ec \
  'createdb --username "$POSTGRES_USER" --maintenance-db postgres "$1"' sh "$RESTORE_DATABASE"

echo "Restoring archive into $RESTORE_DATABASE without modifying the live database..."
if ! "${COMPOSE[@]}" exec -T postgres sh -ec \
  'pg_restore --no-owner --no-acl --exit-on-error --username "$POSTGRES_USER" --dbname "$1"' sh "$RESTORE_DATABASE" \
  < "$backup_file"; then
  echo "Restore into $RESTORE_DATABASE failed. The original database was not changed; inspect and remove the separate restore database after review." >&2
  exit 1
fi

echo "Restore completed into separate database: $RESTORE_DATABASE"
echo "The live application still uses $current_database. Verify the restored database before changing DATABASE_URL/POSTGRES_DB."
