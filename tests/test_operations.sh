#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT
FAKE_BIN="$TMP/bin"
mkdir -p "$FAKE_BIN" "$TMP/home"
export HOME="$TMP/home"
export FAKE_DOCKER_CALLS="$TMP/docker-calls.log"
: > "$FAKE_DOCKER_CALLS"

cat > "$FAKE_BIN/docker" <<'FAKE_DOCKER'
#!/usr/bin/env bash
set -eo pipefail

while [[ "$#" -gt 0 && "$1" != "exec" ]]; do shift; done
[[ "$#" -gt 0 ]] || { echo "fake docker only supports compose exec" >&2; exit 98; }
shift
while [[ "$#" -gt 0 && "$1" == -* ]]; do shift; done
[[ "$#" -gt 0 && "$1" == "postgres" ]] || { echo "unexpected service" >&2; exit 98; }
shift
command_text="$*"
printf '%s\n' "$command_text" >> "$FAKE_DOCKER_CALLS"

if [[ "$command_text" == *"pg_dump"* ]]; then
  if [[ "$FAKE_EMPTY_DUMP" == "1" ]]; then exit 0; fi
  printf 'fake-custom-format-postgres-archive\n'
  exit 0
fi

if [[ "$command_text" == *"pg_restore --list"* ]]; then
  cat >/dev/null
  exit 0
fi

if [[ "$command_text" == *"POSTGRES_DB"* ]]; then
  printf 'campaigns'
  exit 0
fi

if [[ "$command_text" == *"createdb"* ]]; then exit 0; fi
if [[ "$command_text" == *"pg_restore"* ]]; then
  [[ "$FAKE_RESTORE_FAIL" != "1" ]] || exit 19
  exit 0
fi

echo "unexpected fake docker command: $command_text" >&2
exit 98
FAKE_DOCKER
chmod 700 "$FAKE_BIN/docker"
export PATH="$FAKE_BIN:$PATH"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}
pass() { echo "PASS: $*"; }

# Valid archive is created, validated, and stored with restrictive permissions.
BACKUP_DIR="$TMP/backups" bash "$ROOT_DIR/scripts/backup_postgres.sh" >"$TMP/backup.log" 2>&1 \
  || { cat "$TMP/backup.log" >&2; fail "valid backup workflow"; }
backup_file="$(find "$TMP/backups" -maxdepth 1 -type f -name 'campaigns-*.dump' -print -quit)"
[[ -n "$backup_file" && -s "$backup_file" ]] || fail "backup file was not created"
[[ "$(stat -c '%a' "$backup_file")" == "600" ]] || fail "backup file permissions are not 600"
[[ "$(stat -c '%a' "$TMP/backups")" == "700" ]] || fail "backup directory permissions are not 700"
pass "backup creates and validates a restricted custom-format archive"

# An empty pg_dump output must not be installed as a completed backup.
if FAKE_EMPTY_DUMP=1 BACKUP_DIR="$TMP/empty-backups" \
  bash "$ROOT_DIR/scripts/backup_postgres.sh" >"$TMP/empty-backup.log" 2>&1; then
  fail "empty backup unexpectedly succeeded"
fi
if find "$TMP/empty-backups" -maxdepth 1 -type f -name 'campaigns-*.dump' | grep -q .; then
  fail "empty dump was left as a completed backup"
fi
pass "empty backup is rejected"

# Restore must refuse the configured live database before issuing createdb.
: > "$FAKE_DOCKER_CALLS"
if RESTORE_DATABASE=campaigns bash "$ROOT_DIR/scripts/restore_postgres.sh" "$backup_file" \
  >"$TMP/live-restore.log" 2>&1; then
  fail "restore unexpectedly targeted the live database"
fi
grep -q "Refusing to restore over the configured live database" "$TMP/live-restore.log" \
  || { cat "$TMP/live-restore.log" >&2; fail "live database refusal message"; }
if grep -q "createdb" "$FAKE_DOCKER_CALLS"; then
  fail "restore attempted to create a database before rejecting the live target"
fi
pass "restore refuses the live database without creating it"

# A separate restore target should be created and restored to.
: > "$FAKE_DOCKER_CALLS"
RESTORE_DATABASE=campaigns_restore_test bash "$ROOT_DIR/scripts/restore_postgres.sh" "$backup_file" \
  >"$TMP/restore.log" 2>&1 \
  || { cat "$TMP/restore.log" >&2; fail "separate-database restore"; }
grep -q "createdb" "$FAKE_DOCKER_CALLS" || fail "restore did not create the separate database"
grep -q "pg_restore" "$FAKE_DOCKER_CALLS" || fail "restore did not run pg_restore"
pass "restore targets a separate database"

# A failed restore must be surfaced, not reported as successful.
if FAKE_RESTORE_FAIL=1 RESTORE_DATABASE=campaigns_restore_failure \
  bash "$ROOT_DIR/scripts/restore_postgres.sh" "$backup_file" >"$TMP/restore-failure.log" 2>&1; then
  fail "failed restore unexpectedly returned success"
fi
grep -q "The original database was not changed" "$TMP/restore-failure.log" \
  || { cat "$TMP/restore-failure.log" >&2; fail "failed restore safety message"; }
pass "restore errors are surfaced without modifying the live database"
