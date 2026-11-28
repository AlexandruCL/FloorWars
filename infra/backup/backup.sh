#!/usr/bin/env bash
# Scheduled pgBackRest backup (plan 7.7). Runs as root on the VM from floorwars-backup.cron:
#   backup.sh full   weekly (Sunday)
#   backup.sh diff   daily
# Then refreshes the backup-age metric that the "backup older than 26 hours" alert reads.
# WAL archiving (RPO 5 minutes) is continuous inside the postgres container, not in this script.
set -euo pipefail

type=${1:-}
[[ "$type" == "full" || "$type" == "diff" ]] || { echo "usage: backup.sh full|diff" >&2; exit 64; }

c=${POSTGRES_CONTAINER:-floorwars-postgres-1}
start=$(date +%s)
echo "$(date -u +%FT%TZ) backup $type start"
docker exec -u postgres "$c" pgbackrest --stanza=floorwars --type="$type" backup
docker exec -u postgres "$c" fw-backup-metric.sh
echo "$(date -u +%FT%TZ) backup $type done in $(($(date +%s) - start)) s"
