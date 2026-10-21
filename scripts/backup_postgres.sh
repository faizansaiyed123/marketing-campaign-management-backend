set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "$0")/.." && pwd)"
if [[ -z "${BACKUP_DIR:-}" ]]; then BACKUP_DIR="$HOME/campaign-management-backups"; fi
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
COMPOSE=(docker compose --project-directory "$ROOT_DIR" -f "$ROOT_DIR/docker-compose.yml")

if ! [[ "$RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]]; then
  echo "BACKUP_RETENTION_DAYS must be a positive integer." >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="$BACKUP_DIR/campaigns-${timestamp}.dump"
temporary_file="$(mktemp "$BACKUP_DIR/.campaigns-${timestamp}.XXXXXX")"
trap 'rm -f -- "$temporary_file"' EXIT

echo "Creating PostgreSQL custom-format backup..."
"${COMPOSE[@]}" exec -T postgres sh -ec \
  'pg_dump --format=custom --no-owner --no-acl --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' \
  > "$temporary_file"

if [[ ! -s "$temporary_file" ]]; then
  echo "Backup failed: pg_dump produced an empty file." >&2
  exit 1
fi

echo "Validating backup archive..."
"${COMPOSE[@]}" exec -T postgres pg_restore --list < "$temporary_file" > /dev/null
chmod 600 "$temporary_file"
mv -- "$temporary_file" "$backup_file"

if [[ -n "${BACKUP_RCLONE_REMOTE:-}" ]]; then
  if ! command -v rclone >/dev/null 2>&1; then
    echo "BACKUP_RCLONE_REMOTE is set but rclone is not installed." >&2
    exit 2
  fi
  remote_path="${BACKUP_RCLONE_REMOTE%/}/$(basename "$backup_file")"
  echo "Copying backup to configured off-host destination..."
  rclone copyto "$backup_file" "$remote_path"
fi

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'campaigns-*.dump' \
  -mtime "+$RETENTION_DAYS" -delete

echo "Backup created: $backup_file"
if [[ -z "${BACKUP_RCLONE_REMOTE:-}" ]]; then
  echo "WARNING: this backup is only on the current host. Configure BACKUP_RCLONE_REMOTE for off-host copies." >&2
fi
