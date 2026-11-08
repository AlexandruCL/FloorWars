# FloorWars tester guide, Week 3: climb stairs and see the points

You need an Android phone with a barometer (most recent phones have one), the app file from Cristea, and a building with stairs that has a printed FloorWars code at the entrance. The test takes about 20 minutes. You do not need to be near a computer.

## 1. Install

1. Open the app file (`app-release.apk`) on the phone and allow installing from this source if Android asks.
2. Open **FloorWars**. Sign in with your university e-mail, enter the 6-digit code you receive, and pick your team.

## 2. Check in at the building

1. On the **Status** screen, tap **Check in**, then **Scan entrance code**, and point the camera at the printed code at the entrance.
2. Allow the camera, **Physical activity** and **Notifications** when Android asks.
3. You should see "Checked in: <building>, 90 min left" and tap **Done**.
4. On **Status**, **Detection** now reads **Running**, and a notification says the app is counting stair climbs. Leave it running. Do not force-close the app.

If you cannot scan the code, use **Use my location** instead, standing at the entrance.

## 3. Climb

1. Put the phone in a pocket (any pocket), screen off is fine.
2. Walk up at least two floors by the stairs, at a normal pace. Do not take the elevator, do not run, do not shake the phone.
3. Wait one minute at the top.

## 4. Look at the result

Open the app and read **Status**:

| Row | What it should say after a climb |
|---|---|
| Detection | Running |
| Check-in | the building and the minutes left |
| Last segment | a time a minute or two ago |
| Waiting to upload | 1, then 0 after a short while (with a connection) |
| Last upload | the time and "1 uploaded" |

Tap **Sync now** if it still says 1 after a few minutes and you have a connection.

## 5. Report

Send Cristea a message with:

- the phone model and Android version;
- whether each row above matched, and what it said if not;
- a screenshot of **Status**;
- the time you climbed, to the minute (the server logs are by time);
- anything odd: the notification missing, the app closing, a red message on **Status**.

## If something goes wrong

| Problem | What to do |
|---|---|
| **Detection** says "Not running" after checking in | Phone settings, Apps, FloorWars, Permissions: allow **Physical activity** and **Notifications**, then check in again |
| "Camera access is off" | Tap **Open Settings**, allow the camera, come back and scan again |
| "Could not check in. Check your connection..." | Check the mobile data or Wi-Fi, wait a moment, try again |
| **Waiting to upload** does not go down | There may be no connection. It uploads by itself when the connection is back. Red text on **Status** names the problem: send a screenshot |
| No segment after a climb | A climb under two metres, an elevator, or a very fast climb is not counted on purpose. Try another flight of stairs |
| A message about battery saving | Tap **Open battery settings** and set FloorWars to unrestricted, so the phone does not stop the app with the screen off |

**Sign out** (bottom of **Status**) deletes any segments that have not uploaded yet. Do not use it before they upload.
