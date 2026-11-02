# Evaluation

Results of the segmenter and rules classifier on recorded traces (plan section 10, Week 2, and section 11).

## Confusion matrix

Pending: filled in from the real classifier. At this commit `Classifier` is a placeholder that returns `OTHER` for every segment, so the matrix measures nothing yet.

How to produce it: `cd app/android && ./gradlew test`. `TraceReplayTest` (`app/android/app/src/test/java/com/floorwars/floorsensors/classifier/TraceReplayTest.kt`) runs `Segmenter` and `Classifier` on every CSV in `fixtures/synthetic/` and `traces/`, and prints one matrix per folder with per-class precision and recall. It only reads those folders.

Rules used for each trace:

- Expected class, from the label: `stairs_up` is STAIRS, `elevator_up` is ELEVATOR, and `stairs_down`, `walk_flat`, `shake` and `blow` are OTHER.
- Predicted class: STAIRS if any segment is STAIRS, else ELEVATOR if any segment is ELEVATOR, else OTHER.
- The label and placement come from the CSV header and must match the file's row in the folder's `labels.csv`; the test fails otherwise.

## Baseline

Evaluation data: `traces/`, 21 real recordings from two phones, labelled in `traces/labels.csv`.

| Label | SM-S918B | SM-G985F | Total |
|---|---|---|---|
| stairs_up | 1 | 2 | 3 |
| stairs_down | 1 | 3 | 4 |
| elevator_up | 2 | 0 | 2 |
| walk_flat | 1 | 5 | 6 |
| shake | 1 | 2 | 3 |
| blow | 1 | 2 | 3 |
| **Total** | **7** | **14** | **21** |

By placement: hand 13, pocket 6, bag 2 (bag only in `walk_flat`).

Real-data gate (W2-4): open. There are at least 20 real labelled traces and all six labels are present. The set is thin: 3 `stairs_up` and 2 `elevator_up` traces, both elevator rides on one phone (SM-S918B). One misclassified trace moves precision or recall by 0.33 to 0.5, so treat the numbers as a smoke test, not a measurement.

`python tools/validate_traces/validate.py traces` on 2026-11-02: 20 PASS, 1 FAIL (`walk_flat_hand_20261028T215936Z`, check 5, step rate 0.32 Hz; reviewed and accepted on 2026-10-29). Logged in `docs/trace_format.md` section 7.

`fixtures/synthetic/` (24 generated files, 4 per label) is replayed too, but synthetic numbers are not evaluation: the data is generated, and `fixtures/synthetic/README.md` rules it out for evaluating, training or tuning thresholds. The test prints that matrix only to catch regressions.

Numbers and the commit SHA they came from: pending, added with the real classifier.

## Validation log

Each threshold change, with the evidence for it. Don't edit old rows.

| Date | Constant (file) | Old | New | Evidence |
|---|---|---|---|---|
