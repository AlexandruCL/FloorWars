#!/usr/bin/env bash
# Restore drill (plan 7.7, RPO 5 minutes, RTO under one hour). Runs as root on the VM.
# Restores the newest backup plus the archived WAL into a THROW-AWAY container on a scratch
# directory of the data disk, starts it with archiving off and no network port, prints row counts
# and checksums of the four key tables, and the elapsed seconds. It never touches the live
# database or the repository (restore only reads). Paste the output into the runbook ops log.
#
#   restore-drill.sh [<pgbackrest restore args>]   e.g. --type=time "--target=2026-12-01 10:00:00+00"
set -euo pipefail

live=${POSTGRES_CONTAINER:-floorwars-postgres-1}
secrets=${SECRETS_DIR:-/run/secrets/floorwars}
drill_dir=${DRILL_DIR:-/srv/floorwars/data/restore-drill}

image=$(docker inspect -f '{{.Config.Image}}' "$live")
env_of() { docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$live" | sed -n "s/^$1=//p"; }
account=$(env_of BACKUP_AZURE_ACCOUNT)
[[ -n "$account" ]] || { echo "BACKUP_AZURE_ACCOUNT is not set on $live: backups are not configured" >&2; exit 1; }
container=$(env_of BACKUP_AZURE_CONTAINER)

rm -rf "$drill_dir"
install -d -m 0700 "$drill_dir"
trap 'rm -rf "$drill_dir"' EXIT

t0=$(date +%s)
# The inner script runs as root only to write the config from the secrets; every pgBackRest and
# Postgres command runs as postgres. Memory-capped for the 4 GiB VM.
docker run --rm --name fw-restore-drill --memory 1g \
  -v "$secrets":/run/secrets:ro -v "$drill_dir":/drill \
  -v "$(dirname "$(readlink -f "$0")")":/backup:ro \
  -e BACKUP_AZURE_ACCOUNT="$account" -e BACKUP_AZURE_CONTAINER="$container" \
  -e RESTORE_ARGS="$*" --entrypoint bash "$image" /backup/restore-drill-inner.sh
echo "drill total: $(($(date +%s) - t0)) s (RTO target: under 3600 s)"
