# FloorWars phone tests, Week 4: standings, leaderboards and the lost-building alert

You need an Android phone, the app file from Cristea, and a building with a printed FloorWars code at the entrance and stickers on the stair landings. Part 5 needs two testers on different teams, each with a phone, in the same building. The whole test takes about 45 minutes.

## 1. Install and first start

1. Open the app file (`app-release.apk`) and allow installing from this source if Android asks. If an older FloorWars is installed, install over it.
2. Open **FloorWars**. Sign in with your university e-mail, enter the 6-digit code you receive, and pick your team.
3. The **How it works** screen opens once, right after the team choice. Read it to the end. Under **Battery**, follow the steps for your phone, or tap **Open battery settings** and set FloorWars to unrestricted. Then tap **I've read this**.
4. You land on **Status**. Close the app from the recent-apps list and open it again: it opens on **Status**, not on **How it works**. The **How it works** button on **Status** opens the screen again.

## 2. Check in and climb

1. On **Status**, tap **Check in**, then **Scan entrance code**, and scan the code at the entrance. Allow the camera, **Physical activity** and **Notifications** when Android asks. If the code won't scan, use **Use my location** at the entrance.
2. Put the phone in a pocket and walk up at least two floors by the stairs at a normal pace. Wait one minute at the top.
3. Open the app. **Waiting to upload** goes to 1, then back to 0 once it uploads (tap **Sync now** if it stays at 1 with a connection).
4. After the upload, **Verified today** shows the steps and metres of today's counted climbs, for example `Verified today: 84 steps, 12.6 m`. A climb that is still waiting to upload is not in this figure yet.

## 3. Climb history

On **Status**, tap **Climb history**. Check:

| What | What it should show |
|---|---|
| Order | Newest climb on top |
| Each row | Date and time, building, steps, metres, and **Verified**, **Pending** or **Rejected** |
| A verified row | The steps that counted |
| A rejected row | One sentence saying why it didn't count |
| The end of the list | Older climbs load when you scroll down |

## 4. Standings and leaderboards

1. While checked in, tap **Building standings** on **Status**. You see the building name, then `Owned by {team}` or `Nobody owns this building yet`, then one bar split into each team's share in the team colours, then the teams with their points, most points first.
2. Go back and tap **Leaderboards**. Open each tab, **Individual**, **Team** and **Building**, and check that each one lists names and points. The season chips switch the season. On the **Building** tab, the building picker starts on the building you are checked in at.

## 5. The lost-building alert (two testers)

Phone A climbs, phone B watches. The two phones must be on different teams. Agree on the building first.

**Run 1, phone B's app open**

1. Phone B checks in, opens **Building standings** and leaves the screen on.
2. Phone A checks in and climbs until its own **Building standings** shows `Owned by {team A}`. This can take several climbs if team B has many points there.
3. On phone B, without touching the screen: within a few seconds of phone A's upload, the owner line and the bar change to team A's colour.
4. Phone B gets a notification at the top of the screen: **{team A} took {building}**, with the text `Your team lost it. Tap to see the standings.` Tap it: it opens that building's standings.

**Run 2, phone B's app closed**

1. Phone B climbs until team B owns the building again. Phone A gets the same kind of alert this time.
2. Phone B swipes FloorWars away from the recent-apps list and does not check in.
3. Phone A climbs until team A owns the building again. Note the time.
4. Phone B gets the notification within about 15 minutes, because the app checks in the background. Note the time it arrived. Tapping it opens that building's standings.

You get an alert only when your team loses a building, never when it wins, and at most one per building every 10 minutes.

## 6. A phone without a barometer

Only if your phone has no barometer (then **Status** shows **Scan at the stairs**), or Cristea gave you a test build for this.

1. Tap **Scan at the stairs** before checking in. It says: `Check in at the building first, then scan the sticker on a stair landing.`
2. Check in, tap **Scan at the stairs** again. You see `Scan at the stairs of {building}` and **Scan sticker**.
3. Scan a sticker on a stair landing: `Scan counted: +{points} points.`
4. Scan again right away: `You can scan again in this building in 10 min.`

## 7. Report

Send Cristea a message with:

- the phone model and Android version;
- for each part, whether it matched, and what you saw if not;
- screenshots of anything that didn't match;
- the times you climbed, to the minute;
- for part 5, run 2: when phone A took the building and when phone B's notification arrived.

## If something goes wrong

| Problem | What to do |
|---|---|
| No notification in part 5 | Phone settings, Apps, FloorWars, Notifications: allow them, including **Building alerts**. Set the battery to unrestricted (part 1, step 3) |
| The colour didn't change on phone B | Check that phone B has a connection. Go back and open **Building standings** again |
| `Can't reach the server. Check your connection, then pull down to retry.` | Check mobile data or Wi-Fi, then pull the screen down |
| `Last updated {time}. Can't reach the server.` | You see the last copy the app loaded. Pull down once the connection is back |
| `No climbs yet. Check in at a building and take the stairs.` | No climb has uploaded yet. Check **Waiting to upload** on **Status** |
| `This code isn't a FloorWars stair sticker.` | You scanned something else. Scan the sticker on the landing |
| `This sticker isn't for this building, or it has expired.` | Scan a sticker in the building you are checked in at |
| `Too many scans. Try again in {n} min.` | Wait that many minutes |

**Sign out** (bottom of **Status**) deletes any climbs that have not uploaded yet. Don't use it before they upload.
