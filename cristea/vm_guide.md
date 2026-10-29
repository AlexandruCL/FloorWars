# Using the FloorWars server VM (for Cristea)

How to start the backend server, check it, and stop it again from your own computer. Ionut set up the VM; this guide is everything you need to use it.

| What | Value |
|---|---|
| VM | `floorwars-vm` in resource group `floorwars-rg`, Azure subscription "Azure for Students" (Ionut's), region Sweden Central |
| Public IP | `4.223.83.29` (static, does not change when the VM stops) |
| API address | `https://api.4.223.83.29.sslip.io` (temporary name until the real domain works) |
| Health check | `https://api.4.223.83.29.sslip.io/healthz` returns `{"status":"ok"}` |

The VM is **stopped most of the time** to save the student credit. Start it when you need the server, stop it when you are done.

## Part 1. One-time setup

You do steps 1 and 2. Ionut does step 3. After that you never need Ionut to start the server.

### 1. Make an SSH key

PowerShell (Windows). On macOS or Linux use a normal terminal and `~/.ssh/...` instead of `$HOME\.ssh\...`.

```powershell
ssh-keygen -t ed25519 -C "floorwars-cristea" -f $HOME\.ssh\floorwars_cristea
```

Choose a passphrase when it asks, and keep it in your password manager.

### 2. Send Ionut two things

1. Your **public** key, the output of:
   ```powershell
   Get-Content $HOME\.ssh\floorwars_cristea.pub
   ```
   It is one line starting with `ssh-ed25519`. Never send the file without `.pub`: that one is private.
2. Your current **public IP address**, the output of:
   ```powershell
   curl.exe ifconfig.me
   ```
   SSH to the VM is only allowed from known IP addresses.

Also tell Ionut which account you use at <https://portal.azure.com> (your university account `...@student.upt.ro` works best).

### 3. What Ionut does (for reference)

- Gives your Azure account the **Virtual Machine Contributor** role on `floorwars-rg`, so you can start and stop the VM.
- Adds your IP to the Azure firewall rule and to the VM's own firewall.
- Creates your own user `cristea` on the VM with your public key and admin (`sudo`) rights.

Ionut tells you when this is done. Then check you can sign in to <https://portal.azure.com>, search **Virtual machines**, and see `floorwars-vm`. If it is not listed, switch the directory to "Universitatea Politehnica Timisoara" (gear icon, Directories).

## Part 2. Every time you use the server

### 1. Start the VM

Portal, **Virtual machines**, `floorwars-vm`, **Start**. Wait about one minute until **Status** says **Running**.

### 2. Connect

```powershell
ssh -i $HOME\.ssh\floorwars_cristea cristea@4.223.83.29
```

Enter your key passphrase. The first time, answer `yes` to the fingerprint question.

### 3. Start the app

The server's secrets are kept in memory and are gone after every stop, so run the deploy of the current version once after each start:

```sh
sudo /srv/floorwars/deploy.sh "$(cat /srv/floorwars/current)"
```

It takes about 40 seconds and ends with `deploy of <sha> done`.

### 4. Check it

From your computer:

```powershell
curl.exe -i https://api.4.223.83.29.sslip.io/healthz
```

Expected: `HTTP/1.1 200 OK` and `{"status":"ok"}`.

If you get a certificate error, your network's DNS may be answering for the `sslip.io` name (this happened on Ionut's home network). Test past it with:

```powershell
curl.exe -i --resolve api.4.223.83.29.sslip.io:443:4.223.83.29 https://api.4.223.83.29.sslip.io/healthz
```

or set your computer's DNS to `1.1.1.1`. Phones on mobile data are not affected.

On the VM, to see what runs:

```sh
cd /srv/floorwars/repo/infra && export API_TAG=$(cat /srv/floorwars/current)
sudo -E docker compose ps                    # api x2, postgres, valkey healthy, caddy up
sudo -E docker compose logs --tail=50 api    # or caddy, postgres, valkey
```

Always use `sudo -E` with `docker compose`, otherwise it complains that `API_TAG` is missing.

### 5. Point the app at the server

In the app, the API base URL is a placeholder (`app/src/api/client.ts`). For tests against the real server use `https://api.4.223.83.29.sslip.io/v1`. In week 1 only `/healthz` exists; the `/v1` endpoints come from week 2 on. Until then, use the Prism mock (`contracts/prism/README.md`).

### 6. Stop the VM when you are done

Portal, `floorwars-vm`, **Stop**, and wait for **Stopped (deallocated)**. Do not shut it down from inside Ubuntu (`sudo poweroff`): that keeps billing the compute. If auto-shutdown is set (VM, Operations, Auto-shutdown), it is only a safety net: please stop it yourself.

Tell Ionut if you leave it running on purpose (for example for a test with friends' phones).

## If something goes wrong

| Problem | What to do |
|---|---|
| `ssh` hangs or times out | Your IP changed. Run `curl.exe ifconfig.me` and send the new IP to Ionut. |
| `Permission denied (publickey)` | Wrong key file or user. Use `-i $HOME\.ssh\floorwars_cristea` and the user `cristea`. |
| Portal: you cannot see the VM or the Start button is grey | The role is missing or the wrong directory is selected. Ask Ionut. |
| `deploy.sh` fails | Send Ionut the last 30 lines and the output of `tail -n 30 /srv/floorwars/deploy.log`. Do not delete containers or volumes. |
| `/healthz` does not answer after a deploy | `sudo -E docker compose ps` and `sudo -E docker compose logs --tail=50 caddy`, and send them to Ionut. |

## Rules

- Do not change the firewall rules, the Docker setup or files under `/srv/floorwars` and `/etc/floorwars` by hand. Changes go through a PR, like code.
- Never copy `/etc/floorwars/age.key` or anything from `/run/secrets` off the VM.
- Database data lives on the separate data disk. A normal stop and start keeps it.
- Full details for Ionut's side: `docs/runbook.md`.
