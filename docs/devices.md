# Test devices

The two Android phones used for recording traces (T5) and for every on-device check. The plan needs at least two phones with a barometer (IMPLEMENTATION_PLAN.md section 9.3).

Record the exact strings the phone reports, not the marketing name. The app writes manufacturer and model into every trace as `# device_model,<Build.MANUFACTURER> <Build.MODEL>`. Over adb:

```
adb shell getprop ro.product.manufacturer
adb shell getprop ro.product.model
adb shell getprop ro.build.version.release
adb shell getprop ro.build.version.sdk
adb shell dumpsys sensorservice | grep -i -E "pressure|step"
adb shell dumpsys deviceidle whitelist | grep com.floorwars
```

`has_barometer` comes from `getStatus()` in the app, or from a `TYPE_PRESSURE` line in `dumpsys sensorservice`. The battery-optimisation setting is under Settings > Apps > FloorWars > Battery (Unrestricted, Optimised or Restricted). If the app is on the `deviceidle` whitelist, it is Unrestricted.

## Phone 1

Status: tested. 6 traces recorded. Fields marked "not recorded" were not captured during the traces; fill them from the phone.

| Field | Value |
|---|---|
| Manufacturer (`ro.product.manufacturer`) | samsung |
| Model (`ro.product.model`) | SM-S918B (Galaxy S23 Ultra) |
| Android version (release / API level) | not recorded |
| Barometer | Yes. Pressure rows in every trace, about 25 Hz at `SENSOR_DELAY_GAME` |
| Step detector | Yes. Step rows in the stairs and walk traces |
| Battery-optimisation setting for FloorWars | not recorded |
| Manufacturer-specific behaviour seen while recording | Service kept logging with the screen locked for 60 s. Share sheet and CSV export work.  |

## Phone 2

Status: tested. 15 traces recorded. Fields marked "not recorded" were not captured during the traces; fill them from the phone.

| Field | Value |
|---|---|
| Manufacturer (`ro.product.manufacturer`) | samsung |
| Model (`ro.product.model`) | SM-G985F (Galaxy S20) |
| Android version (release / API level) | not recorded |
| Barometer | Yes. Pressure rows in every trace, about 10 Hz at `SENSOR_DELAY_GAME` |
| Step detector | Yes. Step rows in the stairs and walk traces |
| Battery-optimisation setting for FloorWars | not recorded |
| Manufacturer-specific behaviour seen while recording | Service kept logging with the screen locked for 60 s. Share sheet and CSV export work. Pressure arrives at only 10 Hz, and the step detector can lag pressure by up to 240 ms (trace_format.md section 7). |

## Emulator (not a test device)

Used for development checks in T2 to T4 only. Results from it do not count as test-device results, and it must not be listed as one of the two phones. It has no real pressure changes and no step detector, and its power management is not a phone's (no manufacturer battery killers, no real Doze).

| Field | Value |
|---|---|
| AVD | `floorwars_api36` (Pixel 7 hardware profile, 1080 x 2400, 2 GB RAM) |
| System image | Google APIs, x86_64, API 36, revision 7. No Play Store |
| Manufacturer | `Google` |
| Model | `sdk_gphone64_x86_64` (as written to the T4 trace header) |
| Android version | Android 16 (API 36) |
| Barometer | Yes, virtual: `Goldfish Pressure sensor`. Reads a constant 1013.25 hPa unless changed in the emulator's extended controls |
| Step detector | None. Traces from the emulator have no `step` rows |
| Battery-optimisation setting for FloorWars | Not checked; left at the emulator default |

What we saw on it:

- Pressure events arrive at about 50 Hz at `SENSOR_DELAY_GAME` (285 events in 5.7 s in T3; 1487 in 29.75 s in T4).
- With the screen off for about 66 s (T3), the health foreground service stayed in the foreground and kept logging at about 50 Hz while holding its partial wake lock.
- After a cold boot, System UI sometimes shows "System UI isn't responding". Tapping Wait clears it. This is an emulator issue, not an app issue.
