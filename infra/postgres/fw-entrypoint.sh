#!/bin/sh
# Wraps the official entrypoint. Turns WAL archiving on only when BACKUP_AZURE_ACCOUNT is set
# (production). archive_mode with no working repo would fill pg_wal until the disk is full, so
# the settings are command-line flags here and not part of any file in the data directory:
# a restored copy (restore drill) starts with archiving off.
set -eu

# Backup-age metric: 0 until the first successful backup, so the "older than 26 hours" alert
# fires from day one instead of waiting for a metric that does not exist yet.
if [ ! -f /textfile/floorwars_backup.prom ]; then
  printf '# TYPE floorwars_backup_last_success_timestamp_seconds gauge\nfloorwars_backup_last_success_timestamp_seconds 0\n' \
    >/textfile/floorwars_backup.prom
  chown postgres:postgres /textfile/floorwars_backup.prom
  chmod 0644 /textfile/floorwars_backup.prom
fi

if [ "${1:-}" = "postgres" ] && [ -n "${BACKUP_AZURE_ACCOUNT:-}" ]; then
  fw-pgbackrest-conf.sh
  set -- "$@" -c archive_mode=on -c archive_timeout=60 \
    -c "archive_command=pgbackrest --stanza=floorwars archive-push %p"
fi

exec docker-entrypoint.sh "$@"
