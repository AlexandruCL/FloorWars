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

## Cost hygiene

Deallocate the VM when not working on it during development, delete unused disks, IPs and
snapshots. Estimates are in `docs/cost.md`.
