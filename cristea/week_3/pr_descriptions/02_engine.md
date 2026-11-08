## W3-1, W3-3 and the W3-7 gap metric: live segmenter, attribution to the check-in

Stacked on the outbox PR: until that PR merges, the diff also shows its commits.

- **W3-1:** pure-Kotlin `LiveSegmenter` on the existing `Segmenter` and `Classifier` (no second copy of the rules), a 240 s rolling window, each segment emitted once after it closes. `SegmentDetector` stores only STAIRS segments with a pressure-steps match inside the contract bounds and counts the rest. Wired into `FloorSensorsService` as a detect mode with no trace.
- **W3-3:** the active check-in is stored natively and survives a restart. A segment belongs to the check-in active when the climb started. A climb with no check-in is counted, not stored. Detection, sensors and the wake lock stop 201.3 s after `valid_until` so a climb that starts before expiry is stored whole.
- **W3-7 gap metric:** longest pressure gap and number of gaps over 5 s per check-in session, read through `getStatus()`, never uploaded.
- **Permissions:** after a successful check-in the app asks for the sensor permissions before `setActiveCheckin`; a denial still stores the check-in.

### Verify
- `cd app/android && ./gradlew test ktlintCheck`: BUILD SUCCESSFUL, 59 tests, 0 failures
- `cd app && npm run lint && npm run typecheck && npm test`: clean, 10 suites, 82 tests
- Chunked replay equals batch replay on all 45 traces, in 1 s chunks, 5 s chunks and event by event; the trace-replay gate is unchanged. Breaking the emit-once rule fails 9 tests.

### Decisions
`stair_prob` is the constant 1.0 (`RULES_STAIR_PROB`), `classifier_version` is `rules-1`. Sampling is `SENSOR_DELAY_GAME`, sensor batching 5 s, one evaluation pass every 5 s (measured on a desktop only).

### Not verified
Nothing here ran on a phone: the wake lock, the notification text and the stop at expiry. The service is `START_NOT_STICKY`, so after a process kill detection resumes when the app is opened again. The 5 s pass interval has no phone battery measurement yet. If a user denies the activity-recognition permission at check-in and grants it later in Android Settings, detection waits for the next check-in or app start.

On the emulator, a check-in started detection (foreground service, barometer) and the check-in survived a force-stop. The emulator has no step sensor, so no real climb was produced.

Tested against the Prism mock and an emulator only, not the real server.
