#!/bin/sh
# Writes the age metric for the "backup older than 26 hours" alert (W5-6) into the textfile
# directory node_exporter reads: floorwars_backup_last_success_timestamp_seconds, a gauge in
# Unix seconds, no labels. The value is the stop time of the newest backup in the repository
# (as pgBackRest reports it), so a lost repository or a failed run is not hidden. Run as postgres,
# after each backup (infra/backup/backup.sh). No parser in the image: the JSON is flat enough.
set -eu

ts=$(pgbackrest --stanza=floorwars info --output=json | grep -o '"stop":[0-9]*' | tail -n1 | cut -d: -f2)
[ -n "$ts" ] || { echo "fw-backup-metric: no backup found in the repository" >&2; exit 1; }

out=/textfile/floorwars_backup.prom
printf '# TYPE floorwars_backup_last_success_timestamp_seconds gauge\nfloorwars_backup_last_success_timestamp_seconds %s\n' "$ts" >"$out.tmp"
mv -f "$out.tmp" "$out"
