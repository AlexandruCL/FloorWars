# Session D: fake segments, trace replay, end-to-end script

**Name** `w3-d` | **Model** Sonnet 5.5 | **Effort** high | **Branch** `feat/w3-tools` | **Ports** db 55504, valkey 56504 | **Peers** `w3-b` (the rules module), `w3-lead`

Skills to load first: `token-saver`, `trace-check`, `scoring-rules`, `backend-conventions`.

Read: `Ionut/week3/spec.md` sections 1, 3, 4, 11; `docs/trace_format.md` sections 1, 3, 4; `traces/labels.csv` (22 real traces; list the files with `ls`, open at most two to see the format, only the header and the first 15 lines); `tools/fake_segments/fake_segments.py` and its README, `tools/e2e/e2e_check.py`; `contracts/openapi.yaml` `SegmentFields` (field names). The reference segmenter you write is a Python mirror of Cristea's Kotlin one, described in `app/android/app/src/main/java/com/floorwars/floorsensors/segmenter/Segmenter.kt` (read its header comment and the constants only).

## Tasks

1. **Fake-segment script update.** Make `tools/fake_segments/fake_segments.py` match contract 0.5.0 (accepted objects, every rejection reason, a `--device-id`/header source as the contract defines, `--checkin-id` and `--building-id` required) and add kinds that trigger each server rule (`bad_speed`, `bad_cadence`, `bad_ratio`, `out_of_range`, `late`). Keep `--dry-run` and the seed determinism. Tests stay green.
2. **Trace replay (pytest, `server/tests/replay/`).** `reference_segmenter.py` (test-only, say so in its docstring) turns a trace CSV (pressure plus step events) into segments with the fields of `SegmentFields`: median-smoothed pressure converted to altitude (about 0.12 hPa per metre near sea level), climbing windows, step counts per window. `test_replay.py` runs every real trace in `traces/` through `app.segments.rules` (pure functions only, no database) and checks, per `labels.csv`: **no** `elevator_up`, `walk_flat`, `shake` or `blow` trace yields a segment that passes all rules (zero false positives is the gate); `stairs_up` traces: report how many pass. Print a small confusion table (rows = label, columns = passed / rejected with the first failed reason) with `-s`. The recall of `stairs_up` is **reported, not gated** in Week 3 (a TODO to tune with Cristea's evaluation in Week 4). Do not tune thresholds to make traces pass: if one blocks, write the finding in your report instead.
3. **End-to-end script.** Extend `tools/e2e/e2e_check.py` (flag `--upload`): after the check-in, upload a valid fake segment for the checked-in building with a fresh `Idempotency-Key`, expect it accepted; upload it again, expect accepted without `points`; upload a segment with a bad ratio, expect `pressure_steps_mismatch`; read `GET /buildings/{id}/standings` and show the team's points. It must never print tokens or the code.

Steps 1 and 2 need `w3-b`'s `app/segments/rules.py`: start with the reference segmenter and the script, and merge `origin/main` once B's pure rules are on `main` (the lead tells you). Step 3 needs the endpoint on a server (local test stack or the VM): write it, test it against the test app in-process, and leave the live run to Ionut.

## Verify (from the repo root and `server/`, own containers `fw-w3-d-db` 55504, `fw-w3-d-valkey` 56504)

`ruff check --config server/pyproject.toml tools/fake_segments tools/e2e`, `ruff format --check` the same, `pytest -q tools/fake_segments`, `pytest -q server/tests/replay -s` (confusion table in the report, numbers only).

## Report (short)
Branch, commits, verify lines, the confusion table, any trace that disagrees with its label and why.
