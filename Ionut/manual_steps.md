# Week 1 manual steps (Ionut)

Things only you can do: they need your accounts, money, or a phone. Follow them in this order. Each step says what you get at the end and what to tell the agents. Cloud consoles change, so treat button names as hints and check them against the plan (`IMPLEMENTATION_PLAN.md` 7.1, 7.2, 7.2.1).

Never paste keys, passwords or tokens into the chat or into the repo. Where a step produces a secret, it goes into SOPS (step 6) or a password manager.

Estimated time: 3 to 4 hours, most of it waiting for DNS and the VM.

## Order at a glance

| # | Step | Needs | Output |
|---|---|---|---|
| 0 | Prerequisites | GitHub Student Pack, Azure for Students | Accounts ready |
| 1 | Azure budget alert | Azure | Alert at a low threshold |
| 2 | SSH key and age key | Your PC | Keys created |
| 3 | VM, data disk, firewall | Azure | A reachable VM |
| 4 | Harden the VM | SSH | Section 7.1 done |
| 5 | Domain and DNS | Student Pack | `api.<domain>` points at the VM |
| 6 | Firebase project (FCM only), SOPS | Google account | `google-services.json`, encrypted service-account key |
| 7 | Deploy compose, check HTTPS | Agents' files | `/healthz` answers over HTTPS |
| 8 | GitHub: GHCR, secrets | GitHub | CI can push images |
| 9 | Hand-offs to Cristea | Chat | Contract reviewed, `google-services.json` sent, app on both phones |

Steps 1 to 5 can be started while the agents write code. Step 7 needs their `infra/` files.

---

## 0. Prerequisites

1. GitHub Student Developer Pack: <https://education.github.com/pack>. It gives the free domain, GitHub Pro and the Azure for Students offer. Approval can take days, so start it first.
2. Azure for Students: <https://azure.microsoft.com/free/students>. USD 100 credit, no card. Verify the current terms.
3. A Google account for Firebase (use the team's, not a personal one if you have one).
4. A password manager entry named "FloorWars secrets" (the age private key goes here, step 2).
5. Tools on your PC: `ssh`, `git`, `az` (Azure CLI), `sops`, `age`. Install only what you are missing, for example with `winget install Microsoft.AzureCLI`, `winget install FiloSottile.age`, `winget install Mozilla.SOPS`. Check with `az --version`, `age --version`, `sops --version`.

## 1. Azure budget alert (do this first)

Portal: Cost Management + Billing > Cost Management > Budgets > Add.

1. Scope: your student subscription.
2. Amount: for example 20 USD, monthly reset.
3. Alerts: 50%, 80%, 100% of actual cost, plus 100% forecast. Recipient: your e-mail.
4. Save. Also open Subscriptions and note the subscription ID.

CLI alternative once logged in: `az login`, `az account show`.

Tell the agents: nothing. This is a precondition.

## 2. Keys

On your PC (PowerShell):

1. SSH key for the VM: `ssh-keygen -t ed25519 -C "floorwars-ionut" -f $HOME\.ssh\floorwars_ed25519`. Use a passphrase.
2. Separate deploy key for CI: `ssh-keygen -t ed25519 -C "floorwars-deploy" -f $HOME\.ssh\floorwars_deploy -N '""'`.
3. age key for SOPS: `age-keygen -o $HOME\.config\sops\age\keys.txt`. It prints a public key starting `age1...`. Copy the **public** key.
4. Store `keys.txt` (private) in the password manager. Never commit it.

Tell the agents the age **public** key only, so `.sops.yaml` can use it.

## 3. VM, data disk, firewall

Portal: Virtual machines > Create.

1. Resource group: `floorwars-rg`. Region: an EU region (for example West Europe or North Europe). Pick the same region for everything.
2. Image: Ubuntu Server 24.04 LTS. Size: B2s (2 vCPU, 4 GB) or B2ms (8 GB) if the credit allows. Prefer x86 (B-series).
3. Authentication: SSH public key. Paste `floorwars_ed25519.pub`. Username `azureuser`.
4. Inbound ports: allow SSH (22) for now, tighten below.
5. Disks tab: create and attach a new data disk (32 GB is enough), encryption at rest with platform-managed keys. Keep the OS disk default.
6. Networking: create a Standard static public IP. Note the IP.
7. Review + create.

Firewall (Network security group of the VM):

1. Inbound rule 22: source = your current public IP only (and Cristea's if needed). Find your IP with `curl ifconfig.me`.
2. Inbound 80 and 443: source Any.
3. Delete any other allow rule. Leave outbound as is.

Connect: `ssh -i $HOME\.ssh\floorwars_ed25519 azureuser@<VM_IP>`.

Cost hygiene: if you are not working, deallocate the VM in the portal. Delete unused disks, IPs and snapshots.

## 4. Harden the VM (plan 7.1)

Run on the VM. The agents write `docs/runbook.md` with the same commands; if it exists, prefer that.

1. Update: `sudo apt update && sudo apt -y upgrade`.
2. Format and mount the data disk (find it with `lsblk`, usually `/dev/sdc`, **check it is the empty one**): `sudo mkfs.ext4 /dev/sdX`, `sudo mkdir -p /srv/floorwars`, mount it, and add its UUID (`sudo blkid`) to `/etc/fstab`.
3. Create the deploy user: `sudo adduser --disabled-password deploy`. Put `floorwars_deploy.pub` in `/home/deploy/.ssh/authorized_keys` prefixed with `command="/srv/floorwars/deploy.sh",no-port-forwarding,no-pty,no-agent-forwarding `.
4. SSH config `/etc/ssh/sshd_config.d/99-floorwars.conf`: `PermitRootLogin no`, `PasswordAuthentication no`. Then `sudo systemctl reload ssh`. **Keep your current session open and test a second login before closing it.**
5. Firewall: `sudo ufw default deny incoming`, `sudo ufw allow 80,443/tcp`, `sudo ufw allow from <your_ip> to any port 22 proto tcp`, `sudo ufw enable`.
6. `sudo apt -y install unattended-upgrades fail2ban`, then `sudo dpkg-reconfigure -plow unattended-upgrades`.
7. Docker: follow <https://docs.docker.com/engine/install/ubuntu/>, then `sudo usermod -aG docker azureuser`. Check `docker compose version`.
8. Copy only the age **private** key to `/etc/floorwars/age.key` (mode 0400, root-owned).

## 5. Domain and DNS

1. In the Student Pack, claim the free domain (Namecheap or name.com offer). The year starts at redemption, so claim it now.
2. In the registrar's DNS, add an `A` record: `api` -> VM public IP (TTL 300). Optionally `grafana` and `admin` later.
3. Check: `nslookup api.<domain>`.

Tell the agents the domain name so Caddy gets `api.<domain>`.

## 6. Firebase (FCM only) and SOPS

Firebase console <https://console.firebase.google.com>:

1. Add project `floorwars`. Disable Google Analytics.
2. Project settings > Your apps > Add Android app. Package name: `com.floorwars` (this is the `applicationId` in `app/android/app/build.gradle`). Register it.
3. Download `google-services.json`. **Do not commit it.** Keep it for step 9.
4. Project settings > Service accounts > Generate new private key. This downloads a JSON key.
5. Do not enable any other Firebase product (no database, auth, analytics, crashlytics, hosting).

Encrypt the key with SOPS (from the repo root, after the agents create `.sops.yaml` with your age public key):

1. Encrypt straight from the download into the repo: `sops --encrypt $HOME\Downloads\<key>.json > infra/secrets/fcm-service-account.enc.json`. Only `*.enc.*` files under `infra/secrets/` are tracked by git; plaintext there is ignored.
2. Check the file shows `ENC[...]` values, then commit it. Delete the plaintext download from Downloads and the recycle bin.

Other secrets (JWT keys, DB password, QR HMAC key, SMTP) follow the same pattern. The agents will list which ones are needed.

## 7. Deploy and check HTTPS

1. Clone the repo on the VM under `/srv/floorwars` (use a read-only deploy key or HTTPS token for GitHub).
2. Put the decrypted secrets in `/run/secrets` through `deploy.sh` (agents write it; it uses `/etc/floorwars/age.key`).
3. `docker compose up -d --wait` from `infra/`. Caddy fetches a Let's Encrypt certificate on first request. Ports 80 and 443 must be open and DNS must resolve.
4. Check from your PC: `curl -i https://api.<domain>/healthz`. Expected: `200`. This is the week 1 exit.
5. If the certificate fails: `docker compose logs caddy`, check DNS and the NSG.

## 8. GitHub setup

1. Repo Settings > Actions > General: allow workflows, set workflow permissions to "Read and write" only if the image push needs it (GHCR uses `GITHUB_TOKEN` with `packages: write`).
2. Settings > Secrets and variables > Actions: add `DEPLOY_SSH_KEY` (contents of `floorwars_deploy`), `DEPLOY_HOST`, `DEPLOY_USER=deploy`. Add nothing else.
3. Settings > Environments > create `production` with a required reviewer (you or Cristea).
4. Settings > Branches: protect `main` (PR required, one approval, CI green).
5. After the first image push: Packages > the image > Package settings > link it to the repo, visibility private.

## 9. Hand-offs to Cristea

| What | How | Done when |
|---|---|---|
| `contracts/openapi.yaml` review | Open a PR or call, go through the 18 paths and the WebSocket events (`building_flipped`, `season_state`). Check the PR from the contract agent | Both approve |
| `google-services.json` | Send privately (not in git, not in a public chat). Cristea places it at `app/android/app/google-services.json`, which must be git-ignored | Cristea confirms the build still works |
| Fake-segment script and Prism config | Point Cristea to `Ionut/` notes and the agents' README section | Cristea mocks the API with Prism |
| App on both phones | Cristea installs the release APK (`app/README.md`, `cristea/phone_tests.md`) | Both phones run it. Device entries in `docs/devices.md` |
| Real traces | `cristea/phone_tests.md` real-phone work. Week 1 exit allows the 24 synthetic traces if real ones are not ready | Agreed in writing |

## Final check (week 1 exit)

- [ ] `https://api.<domain>/healthz` returns 200
- [ ] `openapi.yaml` merged with both approvals
- [ ] CI green on a PR, image visible in GHCR
- [ ] Budget alert exists
- [ ] Encrypted FCM key in repo, plaintext deleted
- [ ] `google-services.json` sent to Cristea
- [ ] App on both phones (Cristea)
- [ ] 20+ labelled traces in the repo
