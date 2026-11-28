# Backups, restore drill, rollback rehearsal (plan 7.7, W5-7)

How it works: the `postgres` service runs our own image (`infra/postgres/Dockerfile`, postgis 18-3.6
plus pgBackRest). When `BACKUP_AZURE_ACCOUNT` is set, the container starts Postgres with WAL
archiving on (`archive_timeout=60s`, so RPO is about a minute plus upload time, target 5 minutes) and
writes `/etc/pgbackrest/pgbackrest.conf` from two secrets (AES-256, repo on Azure Blob). A weekly
full and a daily differential backup run from the host cron (`floorwars-backup.cron`,
`backup.sh`). Retention: 3 fulls and 7 differentials. After each backup `fw-backup-metric.sh`
writes `floorwars_backup_last_success_timestamp_seconds` into the `backup-textfile` volume, which
node_exporter reads (alert: older than 26 hours; the file holds `0` from the first start, so the
alert fires until the first backup succeeds).

## One-time setup (Ionut)

1. Azure portal: create a storage account in a **second allowed EU region** (not the VM's region):
   Standard, StorageV2, LRS, public blob access disabled, minimum TLS 1.2. Create a private
   container `floorwars-backup`. Copy "Access key 1" (a base64 string) from Security + networking.
2. Create the cipher passphrase: `openssl rand -base64 48`. **Store it in your password manager as
   well.** Without it the backups cannot be read, and it is not recoverable from the VM or Azure.
3. On your PC, in the repo: `sops infra/secrets/backup.enc.env` and write

   ```
   PGBACKREST_AZURE_KEY=<access key 1>
   PGBACKREST_CIPHER_PASS=<the passphrase>
   ```

   Commit it (it stays encrypted). `deploy.sh` turns each key into a secret file; the Week 5 deploy
   refuses to start without both.
4. On the VM, in `/srv/floorwars/repo/infra/.env` add `BACKUP_AZURE_ACCOUNT=<storage account name>`
   (and `BACKUP_AZURE_CONTAINER=` only if the container is not `floorwars-backup`).
5. Deploy as usual (`ssh deploy@<VM_IP> <sha>`). Postgres is recreated once, on the new image, with
   the same data directory; archiving starts. Until step 6 the archive command fails and WAL stays
   in `pg_wal`, so do step 6 straight away.
6. On the VM:

   ```
   docker exec -u postgres floorwars-postgres-1 pgbackrest --stanza=floorwars stanza-create
   docker exec -u postgres floorwars-postgres-1 pgbackrest --stanza=floorwars check
   sudo /srv/floorwars/repo/infra/backup/backup.sh full
   sudo install -m 0644 /srv/floorwars/repo/infra/backup/floorwars-backup.cron /etc/cron.d/floorwars-backup
   docker exec -u postgres floorwars-postgres-1 pgbackrest --stanza=floorwars info
   ```

   `check` must end without an error; `info` lists the full backup and the WAL range. Look at the
   Grafana alert state: "backup too old" clears within a few minutes after the first full backup.

## Restore drill (Ionut, on the VM, about once; record the result)

Restores the newest backup plus the archived WAL into a throw-away container on
`/srv/floorwars/data/restore-drill` (memory cap 1 GiB, no network port, archiving off), counts rows
and checksums `user`, `climb_segment`, `team_building_score` and `game_event`, then deletes the
scratch directory. The live database is not touched. Run it at a quiet time:

```
time sudo /srv/floorwars/repo/infra/backup/restore-drill.sh
```

Paste the whole output into the runbook ops log with the date, the commit and the elapsed times
(files restored, WAL replayed, total). The counts will be a little lower than the live ones (rows
written since the last archived WAL); the checksums only prove the restore reads back real rows.
RTO target: under 3600 s in total. Point-in-time variant:
`restore-drill.sh --type=time "--target=2026-12-01 10:00:00+00"`.

If the drill fails: nothing live was changed. Check `docker logs` of a manual run, `pgbackrest info`,
and that the two secrets and `BACKUP_AZURE_ACCOUNT` are what the running container has.

## Real restore (disaster)

Stop the stack (`docker compose stop api`; postgres too), move the old data directory aside, then run
the restore into the real data directory as the postgres user in a one-off container of the same
image with the same mounts as the `postgres` service (`/var/lib/postgresql` on the data disk and
`/run/secrets`), `pgbackrest --stanza=floorwars restore` (add `--delta` if the directory is not
empty), then start the stack. Rehearse with the drill first: it is the same command with another
`--pg1-path`.

## Rollback rehearsal (Ionut, on his PC with `ssh deploy@<VM_IP>`)

`deploy.sh` times every step in `/srv/floorwars/deploy.log` (UTC timestamps); also use `time`.

1. Note the running tag: `ssh deploy@<VM_IP> true` is not allowed (forced command), so on the VM:
   `cat /srv/floorwars/current /srv/floorwars/last_good`.
2. Deploy `main`: `time ssh deploy@<VM_IP> <sha of main>`. Check `curl -i https://api.floorwars.me/healthz`
   and `tools/e2e/e2e_check.py` as in runbook section 14.
3. Roll back: `time ssh deploy@<VM_IP> rollback`. It re-pins the previous API tag and runs no
   migrations (expand-only migrations keep the old image working). Check `/healthz` and the e2e
   checks that the old version supports.
4. Roll forward: `time ssh deploy@<VM_IP> <sha of main>` again. Check `/healthz` and the e2e.
5. Record the three durations, the tags and the check results in the runbook ops log.

What a rollback does **not** roll back: the Caddy and Postgres images (they follow the `:main` tag,
not the API tag) and database migrations. To pin them for a rollback, set `CADDY_TAG=<sha>` and
`POSTGRES_TAG=<sha>` in `infra/.env` (images are also pushed as `:<sha>`).
