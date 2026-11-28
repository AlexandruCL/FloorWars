# Runbook: VM hardening, first deploy, rollback

Production host for the FloorWars backend (plan 7.1, 7.5, 7.6). Same steps as
`Ionut/manual_steps.md` steps 3, 4 and 7, with the exact commands. Run on the VM as `azureuser`
unless stated. Placeholders: `<VM_IP>`, `<DOMAIN>` (for example `api.example.com`), `<YOUR_IP>`,
`<TEAMMATE_IP>`, `<SHA>` (40-hex git commit on `main`).

Layout on the VM:

| Path | What |
|---|---|
| `/srv/floorwars` | Mount point of the encrypted Azure data disk |
| `/srv/floorwars/repo` | Git clone of this repository (root-owned, checked out at the deployed sha) |
| `/srv/floorwars/repo/infra/.env` | Non-secret settings (`DOMAIN`, `ACME_EMAIL`), from `infra/.env.example` |
| `/srv/floorwars/data/postgres` | PostgreSQL data (bind mount) |
| `/srv/floorwars/deploy.sh` | Reviewed copy of `infra/deploy.sh`, the deploy user's forced command |
| `/srv/floorwars/current`, `last_good` | Running tag and the tag a rollback re-pins |
| `/srv/floorwars/deploy.log` | Deploy history |
| `/etc/floorwars/age.key` | age private key (root, 0400) |
| `/run/secrets/floorwars/` | Decrypted secrets (tmpfs, gone on reboot; `deploy.sh` recreates them) |

## 1. Create the VM (portal)

Follow `Ionut/manual_steps.md` step 3: Ubuntu 24.04 LTS, B2s or B2ms, EU region, SSH key auth
(`azureuser`), a separate 32 GB managed data disk with encryption at rest, a Standard static
public IP, NSG inbound 22 from `<YOUR_IP>` (and `<TEAMMATE_IP>`) only, 80 and 443 from Any.

```sh
ssh -i ~/.ssh/floorwars_ed25519 azureuser@<VM_IP>
sudo apt update && sudo apt -y upgrade
```

## 2. Data disk

Find the empty data disk. **Check the size and that it has no partitions or mount point.**

```sh
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE
sudo mkfs.ext4 -L floorwars-data /dev/sdX        # the empty 32 GB disk only
sudo mkdir -p /srv/floorwars
sudo blkid /dev/sdX                               # copy the UUID
echo 'UUID=<UUID> /srv/floorwars ext4 defaults,nofail,noatime 0 2' | sudo tee -a /etc/fstab
sudo mount -a && df -h /srv/floorwars
sudo install -d -m 0700 /srv/floorwars/data
```

`nofail` keeps the VM bootable if the disk is missing. Then `/srv/floorwars` is an empty
directory on the OS disk; `deploy.sh` refuses to run unless `/srv/floorwars` is a mount point.
After a reboot, check `df -h /srv/floorwars` shows the data disk.

## 3. SSH, firewall, updates, fail2ban

Keep the current SSH session open until a second login works.

```sh
sudo tee /etc/ssh/sshd_config.d/00-floorwars.conf >/dev/null <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
AllowUsers azureuser deploy
EOF
sudo sshd -t && sudo systemctl reload ssh
# from your PC, in a new terminal: ssh -i ~/.ssh/floorwars_ed25519 azureuser@<VM_IP>

sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 80,443/tcp
sudo ufw allow 443/udp                                   # HTTP/3
sudo ufw allow from <YOUR_IP> to any port 22 proto tcp
sudo ufw allow from <TEAMMATE_IP> to any port 22 proto tcp
sudo ufw enable && sudo ufw status verbose

sudo apt -y install unattended-upgrades fail2ban
sudo dpkg-reconfigure -plow unattended-upgrades
sudo systemctl enable --now fail2ban
sudo fail2ban-client status sshd
```

Note: Docker publishes ports through its own iptables chains, which bypass `ufw`. That is why
only Caddy publishes ports (80/443) and the NSG is the outer firewall. Never add `ports:` to
postgres or valkey.

GitHub Actions runners have changing IPs, so CI deploys need port 22 open to them, or a
self-hosted runner / manual deploy. Decide before the first CI deploy (open item).

## 4. Docker Engine and Compose v2

Install from Docker's apt repository: <https://docs.docker.com/engine/install/ubuntu/>
(packages `docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin`).

```sh
sudo usermod -aG docker azureuser        # log out and in again
docker version && docker compose version
sudo apt -y install sops age git curl    # if sops is not packaged, use the release .deb (3.9+)
sops --version && age --version
```

Membership of the `docker` group is root-equivalent. Do not add the `deploy` user to it.

## 5. Repository, age key, registry login

```sh
# Read-only GitHub deploy key for root (repo Settings > Deploy keys, no write access)
sudo ssh-keygen -t ed25519 -N '' -C floorwars-vm-ro -f /root/.ssh/floorwars_github_ro
sudo cat /root/.ssh/floorwars_github_ro.pub     # add in GitHub as a read-only deploy key
sudo tee /root/.ssh/config >/dev/null <<'EOF'
Host github.com
  IdentityFile /root/.ssh/floorwars_github_ro
  IdentitiesOnly yes
EOF
sudo git clone git@github.com:AlexandruCL/FloorWars.git /srv/floorwars/repo

# age private key (paste from the password manager; never commit it)
sudo install -d -m 0700 /etc/floorwars
sudo install -m 0400 -o root -g root /dev/stdin /etc/floorwars/age.key   # paste, then Ctrl-D

# GHCR pull access for root (a classic PAT with read:packages only), unless the package is public
sudo docker login ghcr.io -u <GITHUB_USER>

# Non-secret settings
sudo cp /srv/floorwars/repo/infra/.env.example /srv/floorwars/repo/infra/.env
sudo nano /srv/floorwars/repo/infra/.env        # DOMAIN=<DOMAIN>, ACME_EMAIL=<ACME_EMAIL>
```

Secrets must already be committed as `infra/secrets/*.enc.*` (see `infra/secrets/README.md`).

## 6. Deploy user with a forced command

`deploy.sh` runs as root (it writes `/run/secrets`, sets file owners and calls Docker). The
`deploy` user can only start it, through one sudo rule, with the SSH command as its argument.

```sh
sudo install -m 0750 -o root -g root /srv/floorwars/repo/infra/deploy.sh /srv/floorwars/deploy.sh
sudo adduser --disabled-password --gecos '' deploy
sudo install -d -m 0700 -o deploy -g deploy /home/deploy/.ssh

# authorized_keys: one line, the CI deploy public key (floorwars_deploy.pub)
echo 'command="sudo -n /srv/floorwars/deploy.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA... floorwars-deploy' \
  | sudo tee /home/deploy/.ssh/authorized_keys >/dev/null
sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys && sudo chmod 0600 /home/deploy/.ssh/authorized_keys

# sudo: only this script, no arguments, keep SSH_ORIGINAL_COMMAND (the script validates it)
sudo tee /etc/sudoers.d/floorwars-deploy >/dev/null <<'EOF'
Defaults!/srv/floorwars/deploy.sh env_keep += "SSH_ORIGINAL_COMMAND"
deploy ALL=(root) NOPASSWD: /srv/floorwars/deploy.sh ""
EOF
sudo chmod 0440 /etc/sudoers.d/floorwars-deploy && sudo visudo -c
```

`/srv/floorwars/deploy.sh` is a reviewed copy, not a symlink, so a commit cannot change what
root runs until someone re-installs it (repeat the `install` line after `deploy.sh` changes).
The script accepts only a 40-hex sha that is on `origin/main`, or `rollback`.

## 7. First deploy

The image `ghcr.io/alexandrucl/floorwars-api:<SHA>` must exist (CI pushes it on merge to `main`)
and DNS for `<DOMAIN>` must point at `<VM_IP>`.

```sh
# on the VM
sudo /srv/floorwars/deploy.sh <SHA>
# or from a PC holding the deploy key (what CI does)
ssh -i ~/.ssh/floorwars_deploy deploy@<VM_IP> <SHA>
```

What it does: lock; check out `<SHA>`; decrypt secrets to `/run/secrets/floorwars` (tmpfs, 0400);
pull images; start postgres and valkey; `alembic upgrade head` through the `migrate` service with
the migration role (expand-only; skipped while the image has no `alembic.ini`); `docker compose up -d --wait` with a 90 s limit; record
`current`. If health fails it re-pins the previous tag and exits 1.

## 8. Check health

```sh
curl -i https://<DOMAIN>/healthz                     # from your PC: 200 {"status":"ok"}
cd /srv/floorwars/repo/infra
export API_TAG=$(cat /srv/floorwars/current)          # compose needs it for every command
docker compose ps                                     # 2 api replicas, postgres, valkey healthy
docker compose logs --tail=50 caddy                   # certificate issuance problems show here
docker compose exec postgres psql -U postgres -d floorwars -c 'select public.postgis_version()'
sudo ss -tlnp | grep -E ':(5432|6379)\b' || echo "db ports not published (expected)"
tail -n 30 /srv/floorwars/deploy.log
```

If the certificate fails: DNS (`nslookup <DOMAIN>`), NSG and `ufw` rules for 80/443, and Let's
Encrypt rate limits (use a staging CA while experimenting).

**`/healthz` times out (curl exit 28, no HTTP status).** A timeout means nothing answered; a 404 or 502 would mean
the server is up. Check in this order:

1. VM state in the portal. A deallocated VM (see Cost hygiene) answers nothing. Start it. With a dynamic public IP the
   address changes on start: compare it with the DNS A record (`nslookup <DOMAIN>`) and update the record if they differ.
2. `ssh` in. If it fails but the VM runs: NSG inbound rules for 22, 80, 443, then `sudo ufw status`.
3. After a start or reboot the containers can be down (section 10): `docker compose ps`, then
   `sudo /srv/floorwars/deploy.sh "$(cat /srv/floorwars/current)"`.
4. From the VM: `curl -i https://localhost/healthz --resolve <DOMAIN>:443:127.0.0.1`. Works here but not from outside:
   NSG or DNS. Fails here too: `docker compose logs --tail=50 caddy api`.
5. Once it answers, check that the running tag is the Week 3 release (`cat /srv/floorwars/current`) and that
   `GET /v1/buildings` answers 401 without a token (the route exists).

## 9. Rollback

```sh
ssh -i ~/.ssh/floorwars_deploy deploy@<VM_IP> rollback     # or: sudo /srv/floorwars/deploy.sh rollback
```

Re-pins the sha in `/srv/floorwars/last_good` without running migrations. Migrations are
expand-only (plan 7.7), so the previous image works on the newer schema. A bad classifier
threshold is reverted in the database `config` table, not by a deploy.

`deploy.sh` takes the list of required secrets from the compose file of the tag it checks out,
so a rollback to a pre-Week-2 tag needs only that tag's four secrets. **That tag brings back the
secret files of its own tree, including its `database_url`, which before section 11 is the
superuser `postgres` URL:** the API of that tag runs with full rights again, and the app role
and the `migrate` service are unused until you deploy a Week 2 tag again.

## 10. After a reboot

`/run` is tmpfs, so the decrypted secrets are gone, and containers with `restart:
unless-stopped` fail to start their secret mounts. Re-run the current release:

```sh
sudo /srv/floorwars/deploy.sh "$(cat /srv/floorwars/current)"
```

Later (open item): a systemd unit that runs this at boot.

## 11. Week 2: new secrets and database roles

One-time steps before the first deploy of the Week 2 release. Until they are done,
`deploy.sh` stops before touching the running stack with `missing secret <name>`. Never paste a
password or key into a chat, an issue or a shell history you share.

New secrets (host file name = decrypted name; the API reads each as `/run/secrets/floorwars_<name>`):

| Secret | Used by | What |
|---|---|---|
| `jwt_signing_key`, `qr_hmac_key` | api | Hex keys, already in `infra/secrets/auth.enc.env` (from the auth work) |
| `acs_access_key` | api | Azure Communication Services access key, added by Ionut (step 3) |
| `migration_database_url` | `migrate` service | URL of the migration role (DDL rights) |
| `database_url` | api | Changes to the URL of the app role (no DDL) |

Non-secret settings go in `infra/.env` on the VM: `FLOORWARS_MAIL_BACKEND=acs`,
`FLOORWARS_ACS_ENDPOINT`, `FLOORWARS_MAIL_FROM`, `FLOORWARS_ALLOWED_EMAIL_DOMAINS=student.upt.ro`
(see `infra/.env.example`).

**Order.** Steps 1 to 3 are on your PC, step 4 on the VM, step 5 is the deploy, step 6 the check.
Steps 1 and 2 go together: the same two passwords go into the encrypted URLs and into the roles,
and the `acs_access_key` is added in the same SOPS session so one merge carries all secrets.
Nothing here is typed as a command-line argument, echoed, or kept in shell history.

**1. Choose the two passwords on your PC.** In a second local terminal run `openssl rand -hex 24`
twice and keep the two values in that terminal only (do not write them to a file). Call them
`<APP_PW>` and `<MIG_PW>`.

**2. Edit the encrypted secrets** (`@postgres:5432/floorwars` is the compose host name):

```sh
sops infra/secrets/app.enc.env      # opens the decrypted file in $EDITOR, re-encrypts on save
#   database_url=postgresql+psycopg://floorwars_app:<APP_PW>@postgres:5432/floorwars   (replace the line)
#   migration_database_url=postgresql+psycopg://floorwars_migrator:<MIG_PW>@postgres:5432/floorwars   (new line)
git diff infra/secrets/             # must show only ENC[...] values
```

Do not define a key in two files (`deploy.sh` stops with `secret <key> defined twice`). Commit on a
branch and merge; the VM reads the files from the repo. Nothing changes on the VM until step 5.

**3. Add `acs_access_key`.** Create the Communication Services resource and an Email Communication
Service with a verified (or Azure-managed) sender domain, copy a key from Keys, then
`sops infra/secrets/auth.enc.env` and add `acs_access_key=<key>` (one line). Fill
`FLOORWARS_ACS_ENDPOINT` and `FLOORWARS_MAIL_FROM` in `/srv/floorwars/repo/infra/.env` on the VM.
Create the sender domain and resource before step 5; the deploy refuses to start without the key.

**4. Create the extension and the roles on the VM.** The stack is running (postgres up, Week 1
schema from migration `0001`). Enter the passwords hidden, then pipe them in on stdin together with
`roles.sql` (never as `-v` arguments; `roles.sql` switches statement logging off for its session):

```sh
cd /srv/floorwars/repo && sudo git fetch origin main && sudo git checkout --detach <SHA>
read -rsp 'app password: ' APP_PW; echo
read -rsp 'migrator password: ' MIG_PW; echo
PG=floorwars-postgres-1     # check with: docker ps --format '{{.Names}}'
# extensions are a superuser step; the migrator cannot create them (needed by the check-in migration)
docker exec -i $PG psql -U postgres -d floorwars -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS btree_gist'
{ printf '\set app_password %s\n\set migrator_password %s\n' "$APP_PW" "$MIG_PW"
  cat infra/sql/roles.sql; } | docker exec -i $PG psql -U postgres -d floorwars -v ON_ERROR_STOP=1
unset APP_PW MIG_PW
```

Plain `docker exec` is used because `docker compose` would need every new secret file to exist.
The deploy in step 5 checks out the release again; this checkout only makes `infra/sql/roles.sql`
available. `roles.sql` is idempotent (re-running rotates the two passwords; update the SOPS URLs
to match). It creates `floorwars_migrator` (owns the schema, runs DDL) and `floorwars_app`
(SELECT/INSERT/UPDATE/DELETE and sequence USAGE only; no access to `alembic_version`), moves the
existing tables to the migrator, and sets default privileges so tables created by later migrations
get the app grants. It also sets `search_path = pg_catalog, public` for the `postgres` role in this
database. It was tested locally with `infra/sql/check_roles.sh`.

**Never run DML (INSERT, UPDATE, DELETE) on the app tables as `postgres`.** The `postgres` role
bypasses the app's grants and any later row-level policy, and a superuser session on app tables
is how mistakes become data loss. For a data fix, write a migration or use `floorwars_app` itself.
Superuser sessions are for roles, extensions, backups and read-only inspection.

**5. Redeploy.** `sudo /srv/floorwars/deploy.sh <SHA>` (re-install the reviewed copy first, since
`deploy.sh` changed: see section 6). The deploy now runs `alembic upgrade head` through the
`migrate` service (migration role) and starts the API with the app role. A rollback still never
migrates. The `app` network gets a fixed subnet (`APP_SUBNET`, default `172.29.40.0/24`) so the API
trusts `X-Forwarded-For` only from Caddy; compose recreates the network and containers once. If the
subnet clashes with another network on the VM, set `APP_SUBNET` in `infra/.env`.

If `migrate` cannot start with only its one secret (the API settings require another), the log
names the missing setting: report it, do not widen the mount by hand.

**6. Check after the deploy:** `docker exec floorwars-postgres-1 psql -U postgres -d floorwars -c '\du floorwars_*'`
lists both roles, and the API log shows no `permission denied`.

## 12. Staging

Decision (2026-10-31): **staging is the same VM and the same compose project as production, for now.**
`https://api.floorwars.me` is staging until the first real users exist; there is no second stack, no
second database and no separate `infra/.env`. Reason: one VM on student credit (about $28 a month,
`docs/cost.md`); a second VM or a second Postgres and Valkey would double the cost and the
upkeep for a team of two with no users yet. Consequences to keep in mind:

- A staging deploy is a production deploy. Expand-only migrations (plan 7.7) and the automatic
  re-pin on a failed health check are the safety net; there is no place to rehearse a risky migration.
- Test accounts and the seed data live in the same database that real users will use. Clear them
  before the first real users.
- Revisit when real users exist or a migration needs a rehearsal: a second compose project
  (`-p floorwars-staging`, own data directory, own secrets, hostname `staging.floorwars.me`)
  or a second small VM (plan 7.1, 9.2).

## 13. Week 3 deploy

- The deploy runs migration `0004_segments` through the `migrate` service (migration role), like earlier migrations. It creates `climb_segment` partitions for the current month and the next two.
- The same `migrate` run applies `0005_fk_indexes`: three indexes (`climb_segment(checkin_id)`, `segment_receipt(user_id)`, `fraud_flag(user_id)`), built in the migration's transaction, so writes to those tables wait until it commits.
- Caddy reads its config once at start. The `infra/caddy` folder is mounted (not the single file, which kept the old file after a checkout), and `deploy.sh` ends each release with `caddy reload`. That applies a changed Caddyfile without dropping connections and does nothing when it is unchanged. An invalid Caddyfile fails the reload and the release, and Caddy keeps serving its previous config.
- The first deploy with the folder mount recreates Caddy once (its mounts changed), which also applies the 1MB body cap. Afterwards check that a POST over 1MB gets 413 and that normal requests still work.
- After editing the Caddyfile by hand on the VM: `docker compose ... exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile`.
- `btree_gist` already exists (created in the superuser setup, `infra/sql/roles.sql`); the migration does not create extensions.
- New partitions are created by the migrator, not the app role. Run it monthly until Celery beat does it (Week 5):
  `docker compose ... run --rm migrate python -m app.segments.partitions`
- Rejected-row retention: `app.segments.repository.purge_rejected(db, now)` is not scheduled yet (Week 5 retention job, plan 7.6). Until then, run the equivalent by hand with the migration role if the tables grow (verified receipts are kept):
  `DELETE FROM segment_receipt WHERE status <> 'verified' AND created_at < now() - interval '30 days';`
  `DELETE FROM fraud_flag WHERE (resolved_at IS NOT NULL AND created_at < now() - interval '30 days') OR (resolved_at IS NULL AND created_at < now() - interval '365 days');`
- Leaderboards (`server/app/leaderboards.py`): a season's boards are trusted only while its marker `fw:lb:s{season}:built` exists (1 h expiry). After a Valkey restart or data loss, a failed board update, or an upload that overlapped a rebuild, the marker is missing and the next read rebuilds the season from the database; uploads skip a season without the marker. A rebuild holds `fw:lb:s{season}:lock` (30 s expiry); reads that find it held are computed from the database. While Valkey is unreachable, reads are computed from the database. To force a rebuild: `DEL fw:lb:s{season}:built` in `valkey-cli`. Keep Valkey at `maxmemory-policy noeviction` (the default; `CONFIG GET maxmemory-policy`): an evicted board key with a live marker reads as an empty board.

**Wednesday check (Ionut):**

1. Deploy the Week 3 tag as in section 7 and check health (section 8).
2. Seed: `python tools/seed/seed.py` (idempotent, `tools/seed/README.md`).
3. Do one real climb in the app after a check-in.
4. Run three read-only queries with Run command, as `postgres` inside the postgres container
   (`docker exec floorwars-postgres-1 psql -U postgres -d floorwars -c '<query>'`). `SELECT` only, no DML on app tables:
   - `SELECT status, count(*) FROM climb_segment GROUP BY status;`
   - `SELECT * FROM building_claim;`
   - `SELECT * FROM team_building_score ORDER BY points DESC;`

## 14. Week 4 deploy (Ionut, on the VM)

Not run yet. The Week 3 fixes (#69 to #71) are probably not live either (last known deploy `fbe9c18`); they go out with this one.

1. Back up the database first (section 11 or the backup job; check the dump is non-empty).
2. Pull the Week 4 tag/commit as in section 7.
3. New migration `0006_landing_scan` (landing scans table, expand-only; its downgrade drops all scans) runs through the `migrate` service with the migrator role, as in section 13: `docker compose ... run --rm migrate alembic upgrade head`. Local stack (PR #85): `docker compose -f docker-compose.yml -f compose.local.yml --profile tools run --rm --no-deps -T migrate alembic upgrade head`.
4. Partitions: `docker compose ... run --rm migrate python -m app.segments.partitions`.
5. Deploy (section 7), **both API replicas together**: an old replica publishes events without `season_id`, which a new hub drops (the 15-minute poll covers the gap). `deploy.sh` reloads Caddy. Caddy deletes the `access_token` query parameter from its log; check that a socket opened through Caddy works.
6. `curl.exe -i https://api.floorwars.me/healthz` returns 200.
7. Four checks without a token (401, not 404): `GET /v1/seasons`, `GET /v1/me/events`, `POST /v1/landing-scans`, plus `GET /v1/me/segments`.
8. `python tools/e2e/e2e_check.py --email <you> --qr-token-file <token> --upload` (see `tools/e2e/README.md`).
9. Print the landing stickers (`python tools/qr/make_entrance_qr.py --landing ...`).

**TODO (Week 5): `game_event` retention.** All rows are kept this week. The Week 5 retention job drops rows older than the season end plus 30 days.

## Cost hygiene

Deallocate the VM when not working on it during development, delete unused disks, IPs and
snapshots. Estimates are in `docs/cost.md`.

## 15. Week 5: admin panel (Ionut, on the VM)

Facts from `w5-admin` (branch `feat/w5-admin`); not yet run on the VM. The Week 4 deploy (section 14) comes first.

1. Before the deploy, add `admin_session_key=<output of openssl rand -hex 32>` to a SOPS file in `infra/secrets`. `deploy.sh` reads every top-level compose secret, so it fails without it. `make-local-secrets.sh` writes it locally.
2. In `infra/.env` on the VM (not committed) set `ADMIN_DOMAIN` and `ADMIN_ALLOWED_IPS` (space-separated CIDRs). The defaults are `admin.invalid` and `192.0.2.1/32`, which lets nobody in (403). Add an A record `admin.<domain>` to the VM IP (a DNS action for Ionut).
3. Make an admin: the user signs in once in the app, then run `UPDATE "user" SET is_admin = true WHERE email = '<address>';`. Clearing the flag ends access at once.
4. Rollback of `0008_w5_admin` drops `is_admin`, `paused`, `resolution_note` and `classifier_config` (threshold versions, admin flags and notes are lost).
5. The two Caddy values default in compose (`${ADMIN_DOMAIN:-admin.invalid}`, `${ADMIN_ALLOWED_IPS:-192.0.2.1/32}`), because an empty value makes Caddy refuse the whole Caddyfile, API site included. Changing them needs `docker compose up -d caddy` (recreate), not `caddy reload`. Give the admin domain an A record only, no AAAA: `remote_ip` sees the real client only over IPv4 through Docker's port forward, so an IPv6 client would get 403 (fails closed, but looks like a bug).
6. Local sign-in (local stack only, never on the VM, which uses ACS; checked against a test database, the local stack run is still pending). The `log` mail backend sends no code, so plant one. Sign in once through the app or tools, then from `infra/`:
   - `docker compose -f docker-compose.yml -f compose.local.yml exec -T postgres psql -U postgres -d floorwars -c "UPDATE \"user\" SET is_admin = true WHERE email = '<email>'"`
   - `docker compose -f docker-compose.yml -f compose.local.yml exec -T admin python - <email>` with this script on stdin:
   ```python
   import sys
   from datetime import UTC, datetime, timedelta
   from app.auth import otp, repository
   from app.config import get_settings
   from app.db.session import make_engine, make_sessionmaker
   email, now = sys.argv[1], datetime.now(UTC)
   with make_sessionmaker(make_engine(get_settings().database_url.get_secret_value()))() as db:
       salt = otp.new_salt()
       cid = repository.add_pending_challenge(db, email, otp.hash_code(salt, "123456"), salt, now + timedelta(minutes=10), now)
       repository.activate_challenge(db, email, cid, now)
       db.commit()
   print("code 123456 planted")
   ```
   - Open `https://admin.localhost:8443/admin/` (accept Caddy's internal CA), enter the e-mail and code `123456`.

Sections for backup, restore and rollback wait for `w5-ops-sec`; monitoring for `w5-ops-monitor`.
