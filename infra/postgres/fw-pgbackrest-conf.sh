#!/bin/sh
# Writes /etc/pgbackrest/pgbackrest.conf from the Compose file secrets (pgBackRest has no
# *_file options and environment variables would show in `docker inspect`). Runs as root at
# container start; the file lives in the container's own layer, readable by postgres only.
# Used by fw-entrypoint.sh and by infra/backup/restore-drill.sh.
set -eu

: "${BACKUP_AZURE_ACCOUNT:?set BACKUP_AZURE_ACCOUNT}"
container=${BACKUP_AZURE_CONTAINER:-floorwars-backup}
key=$(cat /run/secrets/pgbackrest_azure_key)
pass=$(cat /run/secrets/pgbackrest_cipher_pass)
if [ -z "$key" ] || [ -z "$pass" ]; then
  echo "fw-pgbackrest-conf: pgbackrest secrets are empty" >&2
  exit 1
fi

umask 077
cat >/etc/pgbackrest/pgbackrest.conf <<CONF
[global]
repo1-type=azure
repo1-azure-account=${BACKUP_AZURE_ACCOUNT}
repo1-azure-container=${container}
repo1-azure-key=${key}
repo1-azure-key-type=shared
repo1-path=/floorwars
repo1-cipher-type=aes-256-cbc
repo1-cipher-pass=${pass}
# Two to four full backups (plan 7.7): 3 fulls and the differentials between them.
repo1-retention-full=3
repo1-retention-diff=7
compress-type=zst
start-fast=y
# 2 vCPU, 4 GiB VM shared with the API: one worker.
process-max=1
log-level-console=warn
log-level-file=info

[floorwars]
pg1-path=${PGDATA:-/var/lib/postgresql/18/docker}
CONF
chown postgres:postgres /etc/pgbackrest/pgbackrest.conf
