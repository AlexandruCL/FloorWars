# Finishing Week 2: the manual steps

The Week 2 code is done and in four pull requests. What is left needs people: reviews, the server, printed entrance codes and a test on real phones. This file lists those steps in order, with the commands. Tick each box when it is done.

Commands are for PowerShell on Windows, run from the repository root unless a step says otherwise. Server facts come from `cristea/vm_guide.md`; read it once before step 3.

## Where things stand (2026-11-02)

| PR | Branch | What | State |
|---|---|---|---|
| #38 | `feat/w2-segmenter` | Segmenter, rules classifier, trace-replay harness, CI precision gate, `app.yml` workflow | CI green, waiting for Ionut's review |
| #39 | `feat/w2-auth` | Sign-in by e-mail code, team choice, Keystore tokens, token refresh | Waiting for review; CI runs after #38 is merged |
| #40 | `feat/w2-checkin` | Check-in screen: QR scan and one-shot location | Contains #39; waiting for review |
| #41 | `feat/w2-staging` | App points at `https://api.floorwars.me/v1`, this guide, the tester guide, README | Waiting for review |

The server side of Week 2 is deployed (README status table). The phone test is the Week 2 exit:

> On a real phone: sign up, pick team, scan entrance QR, see "Checked in: Building X, 89 min left". The segmenter produces a confusion matrix on the traces.

The second sentence is done (`docs/evaluation.md`). The first one is what the steps below are for.

## Step 1. Merge the pull requests, in this order

- [ ] **#38 first.** It brings the app CI workflow (`.github/workflows/app.yml`) and the Jest timeout the other PRs need. Ionut approves, then merge it on GitHub.
- [ ] **Update #39 from main**, so the app CI runs on it. Use the **Update branch** button on the PR page, or from a clone:

  ```powershell
  git fetch origin
  git switch feat/w2-auth
  git merge origin/main
  git push
  ```

  Wait until both checks are green (`android unit tests and trace replay`, `lint, typecheck, test, API client`), get the review, merge.
- [ ] **#40**, the same way, after #39. Once #39 is in main, the #40 diff shrinks to the check-in commits.
- [ ] **#41**, the same way.
- [ ] Bring your local main up to date:

  ```powershell
  git switch main
  git pull
  ```

  Your local main has one commit that is not on GitHub (`6599267`, "updated cristea prompt"). `git pull` merges around it. Push it with a PR if you want to keep it.

## Step 2. Ask Ionut for these

Send this message, or go through it on the Thursday sync:

> Week 2 app side is up for review: #38, #39, #40 (merge after #39), #41. For the phone test I need:
> 1. VM access per `cristea/vm_guide.md` Part 1. I'll send my public key, my IP and my Azure account.
> 2. The real building footprints (#37) seeded on the VM, if they are not there yet: `tools/seed` run against the VM database.
> 3. Printed entrance QR codes for both buildings, from `tools/qr/make_entrance_qr.py --from-db`, valid on the test day.
> 4. Confirmation that the e-mail allow-list is `student.upt.ro` and that sign-in codes arrive.
>
> Not blocking: a contract PR for `accuracy_m` on the geofence check-in, the `urn:floorwars:problem:*` types, 403 examples so Prism can return them, and the `/config` elevator example 1.0 → 0.5 (the client uses 0.5 now; please match it in the server if it keeps its own copy).

- [x] VM access granted (2026-11-02). The laptop used for the test still needs the key from step 3 and its IP on Ionut's SSH rule
- [ ] Real footprints seeded on the VM
- [ ] Entrance codes printed for "Facultatea de Automatica si Calculatoare" and "Facultatea de Mecanica"
- [ ] Allow-list confirmed

Only Ionut can make the codes: they are signed with the server's key, which lives in SOPS. The command he runs (from `tools/qr/README.md`):

```bash
python tools/qr/make_entrance_qr.py --key-file ~/qr.key --out tools/qr/out --from-db --days 7
```

It writes one `<building id>.svg` per building. Codes expire after `--days` (at most 31), so make them close to the test day. Never commit the `.token.txt` files.

## Step 3. One-time VM access

From `cristea/vm_guide.md` Part 1. You do 1 and 2; Ionut does the rest.

1. Make an SSH key. It asks for a passphrase; keep it in your password manager.

   ```powershell
   ssh-keygen -t ed25519 -C "floorwars-cristea" -f $HOME\.ssh\floorwars_cristea
   ```

2. Send Ionut three things:

   ```powershell
   Get-Content $HOME\.ssh\floorwars_cristea.pub   # the public key, one line starting with ssh-ed25519
   curl.exe ifconfig.me                           # your public IP
   ```

   and the account you use at <https://portal.azure.com> (your `@student.upt.ro` account). Never send the key file without `.pub`.

3. When Ionut says it is done, open the portal, search **Virtual machines** and check that `floorwars-vm` is listed. If it is not, switch the directory to "Universitatea Politehnica Timisoara".

- [ ] Key made and sent
- [ ] `floorwars-vm` visible in the portal

## Step 4. Start the server for a test session

The VM is stopped most of the time to save the student credit. Start it only for the test, and stop it after (step 8).

1. Portal, **Virtual machines**, `floorwars-vm`, **Start**. Wait until **Status** says **Running** (about a minute).
2. Connect and start the app on the VM. Its secrets live in memory and are gone after every stop, so this deploy runs after each start (about 40 seconds, ends with `deploy of <sha> done`):

   ```powershell
   ssh -i $HOME\.ssh\floorwars_cristea cristea@4.223.83.29
   ```

   ```sh
   sudo /srv/floorwars/deploy.sh "$(cat /srv/floorwars/current)"
   ```

3. Check it from your laptop and from a phone browser on mobile data:

   ```powershell
   curl.exe -i https://api.floorwars.me/healthz
   ```

   Expected: `HTTP/1.1 200 OK` and `{"status":"ok"}`. A certificate error on home Wi-Fi is a DNS problem on that network (see the vm_guide); mobile data is not affected.

- [ ] `/healthz` returns 200

## Step 5. Build the tester app on your laptop

The app is built here, not on the VM: the VM runs only the server. Build from main after step 1, so the APK matches what is merged.

```powershell
git switch main
git pull
cd app
npm ci
cd android
.\gradlew.bat assembleRelease "-PreactNativeArchitectures=arm64-v8a,armeabi-v7a"
```

- The two architectures cover real phones and keep the file small. The emulator needs `x86_64`; leave the flag out to build all four.
- The APK is `app\android\app\build\outputs\apk\release\app-release.apk`. It carries its own JavaScript, so it runs without Metro or the laptop.
- It is signed with the debug key: fine for testers, not for the Play Store. Do not commit the APK.
- The first build takes 10 to 15 minutes (native code for Vision Camera and Nitro). This release build has not been run to the end yet; only the debug build has. If it fails, send the error before changing anything.

- [ ] `app-release.apk` built

## Step 6. Put the app on the phones

**Your phone, over USB.** Turn on Developer options and USB debugging on the phone, plug it in, accept the prompt on the phone, then:

```powershell
adb devices                    # the phone must be listed as "device"
adb install -r app\android\app\build\outputs\apk\release\app-release.apk
```

If the install fails with a signature mismatch, an older FloorWars build signed with another key is on the phone. Share any sensor recordings from it first, then run `adb uninstall com.floorwars` and install again.

**Testers' phones.** Send each tester two files: `app-release.apk` and `cristea/week_2/tester_guide.pdf`. The guide tells them how to install it, what to tap and what to send back. Before sending:

- Testers need a `@student.upt.ro` address (the allow-list) and must be 18 or older.
- Tell them the test window: the server is only on while you run step 4.
- They pick a team once per season and cannot change it, so tell them which faculty team to pick if it matters for the test.

- [ ] Installed on your phone
- [ ] Sent to testers, with the tester guide and the test window

## Step 7. The phone test (Week 2 exit)

Run this on your own phone first, at the entrance of one of the two buildings, with the printed code there. Write the result next to each line.

| # | Do | Expected |
|---|---|---|
| 1 | Open FloorWars, enter your `@student.upt.ro` address, turn on both switches, tap **Send code** | "Enter code" screen; the e-mail with the 6-digit code arrives |
| 2 | Enter the code, tap **Verify** | "Pick your team" with the faculty teams |
| 3 | Pick your team, tap **Join team** | Home |
| 4 | Close the app completely and open it again | Opens on Home, still signed in |
| 5 | **Check in**, **Scan entrance code**, allow the camera, point at the printed code | "Checked in: Facultatea de ..., 90 min left" and **Done**. The app rounds the minutes up, so it shows 90 right after checking in and 89 a minute later |
| 6 | **Check in**, **Use my location**, allow precise location, standing at the building | "Checked in: ..." for that building |
| 7 | Same, about 100 m away from both buildings | "You are not close enough to a building. Walk to the entrance and try again, or scan the entrance code." |
| 8 | Phone settings, Apps, FloorWars, Permissions: set Camera to **Don't allow**. Then **Scan entrance code**, and tap **Don't allow** if Android asks again | "Camera access is off. Allow it in Settings, or check in with your location." and **Open Settings** opens the app's settings |
| 9 | Same for Location, then **Use my location** | "Location access is off. Allow it in Settings, or scan the entrance code." and **Open Settings** works |
| 10 | Allow the camera again, turn on airplane mode, then scan the printed code | "Could not check in. Check your connection, wait a moment, and try again." |

Do not tap **Skip sign-in (dev)**: it opens the app without an account, for the sensor logger only.

- [ ] Rows 1 to 5 pass on your phone (this is the Week 2 exit)
- [ ] Rows 6 to 10 pass on your phone
- [ ] At least one tester got through rows 1 to 5

## Step 8. Write down the results and stop the server

1. Put the table from step 7, with your results, phone model and Android version, into the #41 description, and the testers' reports under it.
2. Anything that failed: open an issue or tell Ionut, with the screenshot and the time it happened (the server logs are by time).
3. Update the README status row "App, week 2" to say the phone test passed, with the date.
4. Stop the VM: portal, `floorwars-vm`, **Stop**, and wait for **Stopped (deallocated)**. Do not shut it down from inside Ubuntu: that keeps billing. If you leave it running for testers, tell Ionut.

- [ ] Results recorded
- [ ] VM stopped

When step 7's first box and step 8 are ticked, Week 2 is complete.

## If something goes wrong

| Problem | What to do |
|---|---|
| `ssh` hangs or times out | Your IP changed. `curl.exe ifconfig.me` and send the new one to Ionut |
| `Permission denied (publickey)` | Use `-i $HOME\.ssh\floorwars_cristea` and the user `cristea` |
| `deploy.sh` fails | Send Ionut the last 30 lines and `tail -n 30 /srv/floorwars/deploy.log`. Do not delete containers or volumes |
| No sign-in e-mail | Check spam. The address must be `@student.upt.ro` with no `+` alias. Then ask Ionut to check the ACS logs |
| "Could not check in" with the server on | Check `/healthz` from the phone's browser. If it answers, send Ionut the time of the attempt |
| "This code was not accepted" | The printed code is for another key or was edited. Ask Ionut for a fresh one |
| "This code has expired" | Codes expire after the days they were made for, and the app also checks the phone's clock. Check the phone's date and time, then ask for a fresh code |
| Signed out by itself | A refresh token was reused or expired. Sign in again; if it repeats, tell Ionut |

## Not needed for Week 2, but open

- Contract PR (Ionut): `accuracy_m`, the problem types, 403 examples, the `/config` elevator example. See step 2.
- `Team` has no display name in the contract; the team list shows the faculty code and colour.
- There is no sign-out button; it comes with the Home work.
- The elevator threshold (0.5 m/s) rests on two rides in one lift on one phone. Record more rides, in another lift and on the SM-G985F.
