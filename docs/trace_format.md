# Trace format and expected data

What a sensor trace must look like, and what values we expect, so that synthetic and real traces can be checked the same way. Written before the first real recording. Anything marked **TO VALIDATE** is an assumption that the first real phone recordings must confirm or correct.

## 1. File format

One CSV per recording. Produced by the T4 export (`TraceCsv`).

```
# device_model,<Build.MANUFACTURER> <Build.MODEL>
# has_barometer,true|false
# label,<label>
# placement,<placement>
# start_utc,<ISO 8601 UTC, millisecond precision>
# stop_utc,<ISO 8601 UTC, millisecond precision>
sensor,timestamp_ns,elapsed_s,value
pressure,<ns>,<s>,<hPa>
step,<ns>,<s>,1
```

Synthetic files add these lines before the metadata: `# synthetic,true`, `# generator,<path>`, `# seed,<n>`. A real trace has none of them. Its `# device_model` is the phone's real string, never `SYNTHETIC`.

Rules:

- `label` is one of `stairs_up`, `stairs_down`, `elevator_up`, `walk_flat`, `shake`, `blow`.
- `placement` is one of `pocket`, `hand`, `bag`.
- `sensor` is `pressure` or `step`. No other values.
- `timestamp_ns` is the sensor event time from `SensorEvent.timestamp` (elapsed realtime, nanoseconds). It is non-decreasing within the file.
- `elapsed_s` is seconds since the session start (the T4 export writes `(timestamp_ns - session start) / 1e9`), to 3 decimal places. The first row is therefore small but not 0. Checks use differences of `timestamp_ns`, not `elapsed_s` alone.
- `value` for `pressure` is the reading in hPa. For `step` the value is `1`, written as `1.0` by the app.
- No names, locations, or other personal data in any field.

## 2. Expected values

| Quantity | Expected | Basis | Status |
|---|---|---|---|
| Pressure, sea-level-ish | 950–1050 hPa | Weather range at typical elevations | Fixed |
| Pressure per metre of height | ~0.12 hPa/m near sea level | Standard atmosphere (about 12 Pa/m) | Fixed |
| Floor height | ~3–3.5 m | Building norm | TO VALIDATE in the faculty building |
| Pressure change per floor | ~0.36–0.42 hPa | Floor height × 0.12 hPa/m | Follows from the two rows above |
| Pressure sampling rate | ~50 Hz at SENSOR_DELAY_GAME | T3 emulator: 285 events in 5.7 s | TO VALIDATE on phones; devices may deliver slower or faster |
| Step rate while walking | ~1.4–2.1 Hz | Typical adult gait | TO VALIDATE per person |
| Recording length | ~30 s | T4 spec | Fixed |
| Sensor noise (`hand`, `pocket`, `bag`) | ~0.01–0.02 hPa std | Assumption from the synthetic model | TO VALIDATE; likely varies by phone |
| Elevator ramp | 3–6 floors at about 1.0–2.0 m/s, so roughly 9–21 s | Typical lift speed. Earlier 4–6 s figure was too fast (1.75–5 m/s) | TO VALIDATE in the faculty building |

## 3. What each label should look like

Net change is `last pressure − first pressure`, using the first and last second of readings.

| Label | Pressure | Steps | Notes |
|---|---|---|---|
| `stairs_up` | Falls, about 1 hPa per 2–3 floors covered. Several small steps down in pressure, one per flight | Yes, at walking cadence | Landings show as short flat sections |
| `stairs_down` | Rises by the same amount | Yes | Mirror of `stairs_up` |
| `elevator_up` | One smooth ramp down, no step pattern | No, unless the person walks in | Lift start and stop are sharp |
| `walk_flat` | Flat, net change under ±0.1 hPa | Yes | Little drift |
| `shake` | Flat, with noise above the still-phone level | No | Peaks in pressure from movement |
| `blow` | Brief bumps of about 0.3–1.2 hPa | No | Bumps, then back to baseline |

Exact pass/fail thresholds are in the validator (task for Worker). They are kept there so they can be tuned after real data.

## 4. Quality checks

A trace is usable when all of these pass:

1. Format and metadata as in section 1.
2. At least 25 s of pressure readings, and no gaps longer than 1 s.
3. Pressure sampling rate between 20 and 100 Hz.
4. Every pressure value between 800 and 1100 hPa.
5. For `stairs_*` and `walk_flat`: at least one step event, and step rate between 1 and 3 Hz.
6. For `stairs_up` and `stairs_down`: net pressure change of the expected sign and between 0.5 and 3 hPa.
7. For `elevator_up`: net change of the expected sign and between 1 and 4 hPa.
8. `has_barometer` agrees with the pressure rows: `true` if there are pressure rows, `false` if there are none.

Phones without a barometer are out of scope for T5. The plan (section 9.3) requires two phones with a barometer. A trace from a phone with `has_barometer` false can be kept as a record, but it fails checks 2, 3, 6 and 7 by design and doesn't count toward T5.

Failed checks don't delete a trace. They mark it for review.

## 5. Synthetic vs real

- Synthetic traces (under `fixtures/synthetic/`) follow sections 1–4 and must pass the checker. They prove the format and the checker work. They do not prove the sensor model.
- Real traces (under `/traces`) are the only ones that count toward T5 and the exit check.
- After the first phone recordings: compare real values with section 2. For every row marked TO VALIDATE, record the measured value and update this doc. Change the synthetic generator only if the real numbers differ.

## 6. Validation plan

1. Week 1 (now): checker runs on synthetic traces. Must pass all of them.
2. First phone recording (T3/T4 checks): check sampling rate, `has_barometer`, and step events. Update section 2.
3. T5 recordings: run the checker on every file. Record pass/fail per file in `labels.csv` notes.
4. Any mismatch: fix the app (sampling or metadata), the generator (synthetic model), or this doc, in that order of cause.

## 7. Validation log

Add a row each time a phone recording or an app change tests a claim in this doc. Don't edit old rows.

| Date | Source (device or build) | Claim tested | Measured | Change made to this doc or the app |
|---|---|---|---|---|
| — | — | — | — | — |
