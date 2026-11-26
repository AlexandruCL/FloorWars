# FloorWars design

Status: proposal for Week 5, written 2026-11-26. Nothing here is built yet. Mockups of every screen below are on the claude.ai canvas "FloorWars redesign". The current look (`app/src/ui/parts.tsx`) was a stand-in chosen in Week 4 until a design pass.

FloorWars is a stair-climbing territory game for engineering students: you climb for your faculty, and the faculty with the most points in a building over the last 7 days owns it. The design treats the app as the scoreboard of a match that is played in stairwells at night: buildings with their windows lit in team colours, big numbers, and one primary action per screen.

Design read: an Android game app for 19 to 24 year old students playing for their faculty, in a match-day scoreboard language at night. Dials: ENERGY 3, RHYTHM 2, MOTION 2.

Language: English only, in every string and every sample.

## 1. Design context

**Who uses it.** Undergraduates aged 19 to 24 in multi-storey faculty buildings. They open the app for a few seconds between classes, on the stairs, or at home in the evening (remote check-in, Week 5). They identify strongly with their faculty and respond to weekly rivalry and rankings.

**What they come to do.**
1. Check that their climbs will count (checked in, detection running).
2. See whether their team is winning the building they climb for, and by how much.
3. Pick a building to climb for, or switch.
4. Compare themselves and their team on the season tables.

**Personality.** Rowdy, concrete, scoreboard. It should feel like a match day between faculties: loud team colours, confident numbers, short plain sentences. It never shames taking the elevator and never rewards speed.

**Theme.** Dark, by decision: a building's windows only read as lit against a night sky, and the app is often opened in dim stairwells and at night. There is no light theme in this pass.

**Not this.** Not a fitness tracker (no rings, streak flames or calorie counts). Not a dashboard (no stat-card rows, no charts for decoration). Not the generic dark app (no neon, no glow, no purple or cyan gradients).

**Principles.**
1. The game is the first thing you see: your building and who holds it, before any status detail.
2. One primary action per screen. Everything else is a text button or a row.
3. Colour belongs to the teams. The app's own chrome is night neutrals and chalk; the only accent is your own team's colour.
4. Status speaks only when something needs you. A healthy app shows one line of status.
5. Numbers are exact and labelled: points are points, floors are always "floors (estimate)".

## 2. What is wrong with the current UI

Scores use Nielsen's ten heuristics, 0 to 4 each.

| # | Heuristic | Score | Key problem |
|---|---|---|---|
| 1 | Visibility of system status | 2 | Five raw status rows ("Detection", "Last segment") that read "Unknown" when a read fails |
| 2 | Match with the real world | 2 | Engineering words on the main screen: segment, detection, sync |
| 3 | User control and freedom | 2 | Changing building means checking in again; no picker |
| 4 | Consistency and standards | 2 | Navigation, actions and settings all share one full-width button style |
| 5 | Error prevention | 3 | Sign-out warns about climbs not uploaded yet |
| 6 | Recognition over recall | 2 | Building standings appear only while checked in |
| 7 | Flexibility and efficiency | 1 | Seeing your building takes a scroll and a tap past tester tools |
| 8 | Aesthetic and minimalist design | 1 | Seven to nine stacked full-width buttons on Home |
| 9 | Recovering from errors | 3 | Check-in and upload errors name the next step |
| 10 | Help and documentation | 2 | "How it works" is one long wall of text |
| | **Total** | **20/40** | Works, but needs a real design pass |

Verdict on the look: it is the sterile default of a form-based app. Cream ground, one rust accent, the system font, and a 20 px share bar as the only graphic. Swap the name and it could be any form-based app.

Priority issues:

- **[P1] Navigation is a stack of buttons.** `HomeScreen.tsx:273-316` renders Sync now, Check in, Scan at the stairs, Building standings, Leaderboards, Climb history, How it works, Sensor logger and Sign out as equal 52 dp buttons. Fix: a four-tab bar and one primary action per screen (section 4).
- **[P1] The game is hidden.** Owners, shares and the fight only appear behind "Building standings", which shows only while checked in (`HomeScreen.tsx:285`). Fix: the Climb tab opens on your building; a Buildings tab lists them all.
- **[P2] Status rows in engineering words.** `HomeScreen.tsx:219-245`. Fix: one line of status, and a notice only when the player must act.
- **[P2] No identity.** `parts.tsx:12-20` and the 20 px bar at `StandingsScreen.tsx:85`. Fix: night palette, display type, the building drawing.
- **[P2] Motion is missing or untuned.** No pressed state on any `Pressable`; the flip colour change uses the default easing over 600 ms on a 24 dp dot (`StandingsScreen.tsx:51`). Fix: section 9.
- **[P3] Three rows of chips on Leaderboards** (scope, season, building) at `LeaderboardsScreen.tsx:113-137`. Fix: one segmented control, the season in the header, the building as a select row.

## 3. Fewer, lighter buttons

This is the fix for the bulky buttons, applied to every screen:

1. Navigation moves into a bottom tab bar: **Climb, Buildings, Ranks, You**.
2. Each screen has at most one primary button. It is 48 dp tall and as wide as its label, except in a sticky action bar or at the end of a form, where it spans the width.
3. Secondary actions are text buttons (no fill, no border) or list rows with a chevron.
4. A status action lives inside the notice that needs it (for example "Open battery settings" sits in the battery notice).
5. "Sync now" goes. Uploads already run on their own; pull to refresh on Climb also uploads, and an "Upload now" text button appears only while climbs are waiting.
6. Tester tools (Sensor logger) move to You, under "For testers".

Home goes from nine buttons to one primary and at most two text buttons.

## 4. Navigation

```
Tabs (no animation between tabs)
  Climb      your building, today, status          primary: Pick a building (only when not checked in)
  Buildings  every building, who owns it          rows open Building
  Ranks      Players, Teams, In a building        no primary
  You        your season, climbs, settings        no primary
Stack screens (native push)
  Building        drawing, standings, check in    primary: Check in here (sticky)
  History         every climb by day
  Scan entrance   camera, QR check-in
  Scan sticker    camera, landing sticker (no barometer)
  How it works    three steps
  Sensor logger   tester tool
Sheets (bottom sheet over a scrim)
  Pick a building, Confirm check-in, Season
```

The deep link `floorwars://building/{id}` opens Building on top of the Buildings tab, so Back lands on the list.

New dependency: `@react-navigation/bottom-tabs` 7.x, matching `@react-navigation/native` 7.5.1. Sheets are a React Native `Modal` (`Sheet` in `app/src/ui/parts.tsx`). The native `formSheet` from react-native-screens 4.30 was tried first: on Android it dropped taps on its rows and would not open a second time, so it is not used.

## 5. Colour

Neutrals are tinted toward the night-sky hue (262). Values are OKLCH with their sRGB hex. Contrast is WCAG 2 against the named ground.

| Token | OKLCH | Hex | Use |
|---|---|---|---|
| `night` | 0.165 0.018 262 | `#0A0E16` | App background, sky behind buildings |
| `raised` | 0.215 0.022 262 | `#141A24` | Tab bar, sheets, row groups |
| `sunken` | 0.27 0.024 262 | `#202732` | Pressed rows, inputs, your own row in a table |
| `hairline` | 0.32 0.022 262 | `#2D333E` | Separators (decoration only) |
| `edge` | 0.53 0.02 262 | `#666C78` | Borders of inputs and checkboxes (3.66:1 on night) |
| `chalk` | 0.955 0.006 262 | `#EEF0F4` | Primary text; neutral primary button fill |
| `chalkDim` | 0.79 0.018 262 | `#B4BBC6` | Secondary text |
| `chalkFaint` | 0.665 0.02 262 | `#8D94A0` | Meta text, inactive tabs |
| `facade` | 0.255 0.026 262 | `#1C2330` | Building body |
| `facadeLight` | 0.31 0.026 262 | `#29313E` | Parapet and lit edge of a building |
| `window` | 0.2 0.02 262 | `#11161F` | Unlit window |
| `ok` | 0.8 0.15 155 | `#61DA92` | Counted |
| `warn` | 0.85 0.14 85 | `#F8C655` | Needs attention |
| `bad` | 0.72 0.16 28 | `#F9786A` | Not counted, errors, Sign out |

Text contrast, all above 4.5:1:

| Pair | Ratio |
|---|---|
| chalk on night / raised / sunken | 16.9 / 15.3 / 13.2 |
| chalkDim on night / raised / sunken | 10.0 / 9.0 / 7.8 |
| chalkFaint on night / raised | 6.3 / 5.7 |
| ok / warn / bad on raised | 9.9 / 11.0 / 6.6 |
| night text on chalk | 16.9 |

**Team tone.** Team colours come from the server and can be anything an admin typed, `#000000` included. Every team colour passes through one function before it is drawn, so a window always reads as lit on the night ground:

- Keep the hue. Clamp OKLCH lightness to 0.66 to 0.84 and cap chroma at 0.17 (no neon).
- A near-grey colour (chroma under 0.03) stays grey, with lightness clamped to 0.62 to 0.90.
- Reduce chroma until the colour fits sRGB, so the hue never shifts.
- Text on a team tone is `night` or `chalk`, whichever contrasts more.

Checked on real and worst-case inputs:

| Input | Tone | Text on tone |
|---|---|---|
| `#1E88E5` (AC in contract samples) | `#3095F3` | night, 6.2:1 |
| `#E53935` (ETC in contract samples) | `#E86156` | night, 5.8:1 |
| `#F9A825` | `#F9A825` | night, 9.8:1 |
| `#112233` (test seed) | `#8095AA` | night, 6.3:1 |
| `#000000` | `#868686` | night, 5.3:1 |
| `#FFFFFF` | `#DEDEDE` | night, 14.4:1 |

Two teams with close hues can end up close in tone (`#112233` and `#445566` both become grey-blue). Colour is therefore never the only carrier: every tag shows the team code, and the drawing labels its bands.

**Your team is the accent.** The primary button, your row in tables and the "You" markers use your team's tone. Before a team is chosen (sign-in, team pick) the primary button is chalk with night text.

## 6. Type

| Role | Family | Size / line height | Use |
|---|---|---|---|
| `display` | Big Shoulders Stencil Display 900 | 64 / 60 | One hero numeral per screen: today's floors, your rank |
| `title` | Big Shoulders Display 800 | 34 / 36 | Screen titles, building names |
| `heading` | Big Shoulders Display 800 | 24 / 28 | Section headings, team codes |
| `body` | Barlow 400 | 16 / 25 | Sentences |
| `label` | Barlow 600 | 16 / 22 | Row titles, buttons, table figures |
| `meta` | Barlow 500 | 13 / 18 | Timestamps, captions, units |

Why these: Big Shoulders comes from city signage, narrow and loud like a scoreboard, and its stencil cut echoes the floor numbers painted on stairwell walls. Barlow comes from highway signs, so the pair shares one signage voice, and it stays readable at a glance. Both are SIL Open Font License files from Google Fonts and include accented Latin letters.

Rules:

- Numbers in a column or numbers that change live use Barlow 600 with `fontVariant: ['tabular-nums']`. Big Shoulders has proportional digits only (checked: no `tnum` feature), so it is for single display numbers.
- The stencil face is only for the one hero numeral, never for words.
- Sentence case everywhere. Team codes stay as the server sends them.
- Respect the system font scale: no fixed heights around text.

Files (`app/assets/fonts/`, linked with `react-native.config.js` and `npx react-native-asset`): `BigShouldersDisplay-ExtraBold.ttf`, `BigShouldersStencilDisplay-Black.ttf`, `Barlow-Regular.ttf`, `Barlow-Medium.ttf`, `Barlow-SemiBold.ttf`. On Android each weight is its own `fontFamily` name.

## 7. Space, shape, touch

- Spacing scale (dp): `xs` 4, `sm` 8, `md` 12, `lg` 16, `xl` 24, `xxl` 32, `xxxl` 48. Screen gutters `lg`. Related items `sm` to `md` apart; sections `xxl` apart.
- Radius: `sm` 4 (team tags), `md` 12 (buttons, inputs, row groups), `lg` 20 (sheet top corners). Nothing is pill-shaped.
- Elevation: a lighter surface sits higher. Only sheets add a scrim.
- Touch: every target at least 48 dp tall (Android), text buttons padded to 48 dp, 8 dp between neighbouring targets.

## 8. Components

**Button.** `primary`: 48 dp, radius `md`, padding 20 dp, Barlow 600 16, team tone fill (chalk before a team exists) with the tone's text colour. `text`: no fill or border, chalk text, padding to 48 dp. `danger`: a text button in `bad`. Disabled: `sunken` fill and `chalkFaint` text, never a faded copy. Busy: a spinner takes the label's place at the same width, so the button does not jump. The outlined secondary style is removed.

**Row.** Min 56 dp. Title Barlow 600 16, optional subline `meta` in `chalkDim`, trailing value in `chalkDim`, chevron in `chalkFaint`. Grouped rows sit on `raised` with radius `md` and inset hairlines. Used for navigation and settings.

**TeamTag.** The team code in Big Shoulders 800 on the team tone, radius `sm`. Small (16 px text, 24 dp tall), medium (20 px, 32 dp), jersey (56 px, 72 dp square) for You and team pick.

**Notice.** A status message that needs the player: `raised` surface, a 20 dp pictogram in `warn` or `bad`, one sentence in chalk, one text button. The whole surface carries the state; there is no coloured side stripe.

**Segmented control.** Ranks scope. `raised` track, active segment `sunken` with chalk text and a 1 dp `edge` border, inactive `chalkDim`. 48 dp tall.

**Pictograms.** One small set drawn in-house with react-native-svg, filled shapes in the style of public signage, 24 dp grid: stairs (Climb), building (Buildings), table (Ranks), shirt (You), chevron, check, clock, cross, alert, battery, camera, lock, flag. No icon library.

**Flip banner.** Shown in the app when a `building_flipped` event arrives in the foreground: the new owner's TeamTag, "ETC took Faculty of Mechanical Engineering", and when your team lost it the approved line "Your team lost it. Tap to see the standings." Tap opens Building. It closes after 5 s or on an upward swipe.

## 9. The building drawing

Possible with today's code and no server change: `GET /buildings` gives the id and name, `GET /buildings/{id}/standings` gives the owner and every team's points, `react-native-svg` and Reanimated are installed, and `barSegments` in `app/src/standings/bar.ts` already turns points into shares.

**Shape from the id.** Buildings have no geometry in the API, so each one gets a facade generated from a seeded random from its id. The same id always draws the same building; different ids differ.

- Floors 4 to 8, bays 3 to 6.
- Roof: flat parapet, stair housing on the left, stair housing on the right, or a gable.
- Window shape: tall, square or wide.
- A door replaces the middle ground-floor window.

**Windows lit by share.**

- Window count = floors times bays, minus the door.
- Each team with points gets windows in proportion to its share (largest remainder method), and at least one window, so a small team never disappears. If there are more teams than windows, the top teams get one each and the rest stay in the table.
- Windows fill from the ground floor up, left to right, in standings order: most points first, and on a tie the current owner first (the owner keeps a building on a tie).
- The owner's flag stands on the roof in the owner's tone with the code on it. A building without an owner has a bare roof.
- In the large drawing each team's band gets its code beside the facade at the band's middle, so the drawing works without colour.
- No points in the last 7 days: every window unlit, and the line "No team has points here in the last 7 days. Climb the stairs to claim it."

Accessibility label: "Faculty of Mechanical Engineering. Owned by ETC. ETC 48 percent, AC 41 percent, MEC 11 percent."

**Sizes.** Hero: full width, about 200 dp tall on Climb and 240 dp on Building, with band labels and the flag code. Thumbnail in the Buildings list: 48 by 64 dp, no labels.

**Code.** About 150 lines plus tests:

- `app/src/standings/facade.ts`: `facade(id)` and `allocateWindows(teams, count)`, pure functions.
- `app/src/standings/BuildingDrawing.tsx`: the SVG.
- Tests: allocation always sums to the window count, every team with points gets a window, ties put the owner first, and the same id gives the same facade.

It replaces the 20 px bar on Standings and is reused on Climb, Buildings, the check-in sheet and the sign-in skyline (neutral lit windows).

## 10. Screens

Every data screen has loading, empty and error states. Errors say what failed and what to do; pull to refresh retries.

### Climb (tab 1)

The job: "Do my climbs count, and are we winning my building?"

Checked in:

1. Top line: your TeamTag and "Season 3, ends Sunday" (from `GET /seasons/active`).
2. Your building drawn large, then its name.
3. The fight line, derived from standings: "AC owns it and leads ETC by 132 points." / "ETC owns it. AC needs 133 points to take it." / "Tied at 310 points. AC keeps it until someone pulls ahead." / "Nobody owns it yet."
4. Under a "Last 7 days" label, the top three teams as rows: TeamTag, points, share. The text button "All standings" opens Building.
5. Check-in line: "Checked in, 21 h left" with the text button "Switch building". While switching is locked: "You can switch at 14:20 tomorrow".
6. Today: the stencil numeral with "floors (estimate)" beside it, then "412 verified steps, 61.2 m up". Tap opens History.
7. Status: one line in meta type when healthy, "Detection on. Last upload 14:02." Otherwise up to two notices, in this order: no barometer, detection off, battery restriction, upload problem. Climbs waiting with no problem: "3 climbs waiting to upload." with "Upload now".

Not checked in: an unlit building, "Pick a building to climb for", "Your climbs count for the building you check in to, for 24 hours.", primary **Pick a building**, text button **Scan entrance code**.

No barometer: the notice "This phone can't measure height. Scan the sticker on a stair landing after you climb." with **Scan stair sticker**.

Sensor service unreadable: "Couldn't read the sensor service. Close and reopen the app." with **Try again**.

### Buildings (tab 2)

1. Title "Buildings".
2. The score: buildings held per team as TeamTags with counts, most first, then "2 open". Computed from the same standings calls as the list.
3. One row per building: thumbnail drawing, name (wraps to two lines), owner line (the owner's TeamTag and its lead, "leads by 89" or "tied at 310, keeps it", or "Open, no points this week"), and "You're here" on the building you are checked in to. Your building first, then by name.

States: names arrive with `GET /buildings`, thumbnails stay unlit until each standings call returns. Error: "Couldn't load the buildings. Pull down to try again." Empty: "No buildings are set up for this season yet."

Cost: one standings call per building. Fine for the pilot's one or two buildings; past about 20 a list endpoint with owners would be needed (open question).

### Building (stack)

1. The drawing as the hero, with band labels and flag.
2. Name, then "Owned by ETC since Tuesday 14:02" (from `claimed_at`) or "Nobody owns it yet".
3. The fight line, as on Climb.
4. Standings table: rank, TeamTag, points, share, and for every team but the owner "To take it": the leader's points minus theirs plus one.
5. "Points from verified climbs in the last 7 days. The team with the most points owns the building."
6. Sticky action bar: **Check in here**. Already checked in here: "You're climbing here, 21 h left" and no button. Locked to another building: the button disabled and "You can switch at 14:20 tomorrow".

Live: a flip for this building replays the drawing (section 11) and the rows move to their new order.

### Check-in

- **Pick a building** opens a sheet with the Buildings rows. Tapping one opens the confirm sheet: thumbnail, "Check in to Faculty of Mechanical Engineering?", "Your climbs count here for 24 hours. You can't switch to another building until 14:20 tomorrow.", **Check in here**, text button **Cancel**. Checking in again to the same building says "Renew for 24 hours".
- **Scan entrance code** keeps today's camera flow on a full-screen dark camera view with one line: "Point the camera at the code by the entrance."
- Success: back on Climb, the building's windows light from the ground up (section 11).
- `403 building-locked`: "You switched building at 14:20 yesterday. You can switch again at 14:20 today."

This uses the Week 5 remote check-in (`method: pick`, 24 h check-ins, 24 h switch lock).

Before Week 5 ships, the redesign keeps today's check-in rules:

- Check-ins last 90 minutes ("Checked in, 74 min left") and there is no switch lock, so the locked lines and the confirm sheet wait for Week 5.
- Pick a building opens the Buildings tab, and Check in here on Building opens the check-in screen.
- The check-in screen keeps both of today's methods: **Scan entrance code** as the primary button and **Use my location** as a text button.

### Ranks (tab 3)

1. Title "Ranks", season at the right ("Season 3", opens the season sheet).
2. Segmented control: **Players**, **Teams**, **In a building**.
3. Rows: rank, name or TeamTag, points (tabular). Your row on `sunken` with a "You" tag. If you are outside the visible rows, a pinned row at the bottom from `GET /me/season-stats`: "You, 63rd, 412 points".
4. In a building: a select row with the building name above the table, opening the building sheet.

Empty: "No points on this board yet this season."

### You (tab 4)

1. Jersey TeamTag, "You climb for AC", "Season 3, ends Sunday 30 November".
2. Season figures from `GET /me/season-stats`: floors (estimate) as the stencil numeral, then points and rank in Big Shoulders 800.
3. "Recent climbs": the last three, then the row **All climbs**.
4. Settings rows: **Keep detection running** (shows "Allowed" or "Restricted" and opens battery settings), **How FloorWars works**.
5. "For testers": **Sensor logger**.
6. **Sign out** as a danger row, with today's confirmation that names climbs not uploaded yet.

Week 5 privacy rows (export, delete account) join the settings group once they exist.

### History (stack)

A list grouped by day with sticky headers ("Today", "Yesterday", "Monday 23 November"). Each row: time (tabular), building, "86 steps, 12.4 m up", and the status with a pictogram and a word: **Counted** (with "80 steps scored" when fewer than climbed), **Pending**, **Not counted** followed by the approved reason text from `app/src/history/reasons.ts`. Status is never colour alone.

Empty: "No climbs yet. Check in at a building and take the stairs."

### How it works (stack, first run after team pick)

Three short steps with Next, "1 of 3" in the header:

1. **Walk, don't run.** The approved safety copy.
2. **What FloorWars uses.** Physical activity, notifications, camera, one line each. Location goes with the geofence button in Week 5.
3. **Keep it running.** The phone maker's battery steps from `batterySteps()`, **Open battery settings**, then **Start climbing**.

### Sign in, code, team

- Sign in: the FloorWars wordmark set in Big Shoulders (type only until a real logo exists), a strip of neutral lit buildings, "Climb for your faculty", the email field, two checkbox rows ("I am 18 or older", "I accept the terms and privacy notice"), **Send code**. Checkboxes replace the switches: a switch means "takes effect now", a consent is a checkbox.
- Code: one field with spaced tabular digits, **Verify**, text button **Send a new code**.
- Team: two columns of jersey tags. Selecting one makes the button **Join AC**; before that it reads **Pick a team** and is disabled. "One team per season. You can't change it later."

## 11. Motion

Every animation passed four checks: how often it is seen, what it is for, whether it stays under budget, and whether it moves data people are reading.

| Moment | How often | Purpose | Motion |
|---|---|---|---|
| Press on any button or row | Tens a day | Feedback | Scale to 0.97 on press-in, 100 ms; back on release, 160 ms; ease-out `(0.23, 1, 0.32, 1)` |
| Tab switch | 100+ a day | None | No animation |
| Push and pop | Tens a day | Spatial | Native stack default |
| Sheets | Occasional | Spatial | Slide up from the bottom over a scrim |
| Flip in the building on screen | Rare | State, delight | New colours replace old floor by floor from the ground up, 180 ms per floor, 40 ms apart, ease-out; flag crossfades and rises 6 dp in 200 ms; whole thing under 600 ms |
| Check-in success | About daily | Delight | Windows go from unlit to lit floor by floor, 160 ms each, 30 ms apart |
| Flip banner | Occasional | Spatial | Slides down 220 ms ease-out; leaves upward 160 ms; a fast upward flick dismisses it |
| Standings reorder after a flip | Rare | Prevents a jump | Rows move with `LinearTransition`, 200 ms, ease-in-out `(0.77, 0, 0.175, 1)` |

How: press feedback and the banner use Reanimated CSS transitions on `transform`; the flip draws the new allocation as a second layer of floor groups and animates each group's opacity, so only about eight values animate, never one per window. Nothing animates width, height or margins.

Reduced motion (`useReducedMotion`, `ReduceMotion.System`): the flip and the check-in become a 150 ms opacity crossfade, the banner fades without sliding, presses keep only the colour change.

Rejected: list entrance staggers on Ranks and History (seen tens of times a day, and it moves data being read), skeleton shimmer (an endless loop), a pulsing live dot (an endless pulse), a ticker on points (the flip already shows the change), parallax on the building (decoration), a sliding tab indicator (tabs never animate).

Haptics, optional: a confirm pulse when your team takes a building in the foreground, a reject pulse when it loses one, fired in the same frame as the visual. No haptics library is installed; a `performHaptic(kind)` method on the existing Kotlin module (`View.performHapticFeedback`) is the smallest way.

## 12. Words

- Buttons are a verb and an object: Pick a building, Check in here, Scan entrance code, Upload now, Open battery settings, Join AC, Send code.
- One term per idea. "Check in" for the act, "climb" for a recorded ascent, "points" for score, "floors (estimate)" for the display estimate. "Segment" and "sync" never reach the player.
- Errors say what happened and what to do next, and blame nobody. Keep the approved strings: rejection reasons, the loss notification, the safety copy.
- Exclamation marks, emoji and em dashes stay out of the app.

## 13. Data that must not break it

| Field | Worst realistic case | Rule |
|---|---|---|
| Building name | "Faculty of Electronics, Telecommunications and Information Technologies" | Wrap to two lines in rows, three under the hero; never truncate on Building |
| Building name missing | `GET /buildings` down | "Building 12", as today |
| Team code | Contract has no length limit | Tags grow with the code; band labels drop when they would overlap |
| Team colour | `#000000`, `#FFFFFF`, two near-identical colours | Team tone (section 5) plus codes |
| Points | 0, 1, 12,480 | "1 point", "0 points"; thousands separators; tabular |
| Teams in a building | 1, 3, 12 | At least one window each while windows last; the table lists everyone |
| Owner | null, tie with the leader | No flag; owner first on a tie |
| Lists | 0 rows, 1 row, 50 rows | Empty states; Ranks shows 50 and pins your row |
| Font scale | 200 % | Rows grow, nothing has a fixed height around text |

## 14. Build order

The smallest path, each step shippable:

1. Tokens and fonts: replace `colors` in `parts.tsx`, add the font files. Every screen changes look at once.
2. Components in `parts.tsx`: Button variants, Row, TeamTag, Notice, pictograms. Remove the outlined button.
3. Navigation: bottom tabs, move Home's rows into You, Leaderboards becomes Ranks, Standings becomes Building, deep link updated.
4. The building drawing (section 9) with its tests.
5. Screens in order of use: Climb, Building, Buildings, Ranks, You, History, the check-in screen restyled with today's methods (the pick and confirm sheets come with remote check-in in Week 5), How it works, sign-in.
6. Motion (section 11).

Tests that change with the new labels and structure: `HomeScreen`, `history`, `leaderboards`, `onboarding`, `signout`, `standings`, `checkin`, `AuthScreens`, `landingScan` and `App` in `app/__tests__`.

## 15. Open questions

- A list endpoint with each building's owner and top shares, if the number of buildings grows past the pilot.
- A real logo. Until then the wordmark is type only.
- Haptics on the native module, or none.
- Whether Sensor logger stays visible in the v1.0 release build or only in debug builds.

## 16. Why each decision

- Dark night palette: lit windows need a night sky, and players open the app in stairwells and at night.
- Your team as the only accent: wearing your colours is the match-day signal, and it keeps the app's chrome from competing with team colours.
- Lit windows as the motif: it shows ownership and shares as the building itself, from data the app already has.
- Big Shoulders with Barlow: both come from signage, which fits buildings and stairwells, and both read at a glance.
- Stencil numerals: the painted floor numbers of a stairwell, used once per screen.
- Tabs over a button list: four places to go, always one tap away, and the screens stop competing for the first screen.
- Rows instead of cards: lists and settings are grouped by space and one shared surface, so no screen turns into a stack of boxes.
- Pictograms drawn in-house: signage shapes match the type, and a stock icon set would not.
