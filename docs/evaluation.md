# Evaluation

Results of the segmenter and rules classifier on recorded traces (plan section 10, Week 2, and section 11).

## Confusion matrix

How to produce it: `cd app/android && ./gradlew test`. `TraceReplayTest` (`app/android/app/src/test/java/com/floorwars/floorsensors/classifier/TraceReplayTest.kt`) runs `Segmenter` and `Classifier` on every CSV in `fixtures/synthetic/` and `traces/`, and prints one matrix per folder with per-class precision and recall, then one `miss` line per misclassified trace with its segments. It only reads those folders.

Rules used for each trace:

- Expected class, from the label: `stairs_up` is STAIRS, `elevator_up` is ELEVATOR, and `stairs_down`, `walk_flat`, `shake` and `blow` are OTHER.
- Predicted class: STAIRS if any segment is STAIRS, else ELEVATOR if any segment is ELEVATOR, else OTHER.
- The label and placement come from the CSV header and must match the file's row in the folder's `labels.csv`; the test fails otherwise.

Real traces (`traces/`), the evaluation set:

```
Trace replay: traces, 21 files
true label      STAIRS  ELEVATOR     OTHER  expected
stairs_up            3         0         0  STAIRS
stairs_down          0         0         4  OTHER
elevator_up          0         2         0  ELEVATOR
walk_flat            0         0         6  OTHER
shake                0         0         3  OTHER
blow                 0         0         3  OTHER
class              precision          recall
STAIRS            1.00 (3/3)      1.00 (3/3)
ELEVATOR          1.00 (2/2)      1.00 (2/2)
OTHER           1.00 (16/16)    1.00 (16/16)
```

Synthetic fixtures (`fixtures/synthetic/`), a regression check only, not evaluation:

```
Trace replay: fixtures/synthetic, 24 files
true label      STAIRS  ELEVATOR     OTHER  expected
stairs_up            4         0         0  STAIRS
stairs_down          0         0         4  OTHER
elevator_up          0         4         0  ELEVATOR
walk_flat            0         0         4  OTHER
shake                0         0         4  OTHER
blow                 0         0         4  OTHER
class              precision          recall
STAIRS            1.00 (4/4)      1.00 (4/4)
ELEVATOR          1.00 (4/4)      1.00 (4/4)
OTHER           1.00 (16/16)    1.00 (16/16)
```

## Baseline

The numbers above come from commit `d3e4951` on `feat/w2-segmenter` (segmenter v1, rules classifier v1 with the plan 3.3 thresholds and `MIN_ELEVATOR_SPEED_MPS` at 0.5), run on 2026-11-02. No trace is misclassified, so neither matrix has `miss` lines. At `9e0deca`, with the elevator threshold at 1.0 m/s, both real rides were OTHER (see the Validation log).

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

Result on real traces: every trace gets its expected class, and no trace earns false points. The elevator rides (0.586 and 0.693 m/s) sit inside the stairs speed band, so only their missing steps keep them out of STAIRS. The stairs climbs sit closest to these limits: vertical speed 0.167 to 0.194 m/s against the 0.1 m/s floor, and 4.35 steps per metre (`stairs_up_hand_20261025T164024Z`) against the 4.0 floor.

CI gate: `TraceReplayTest.realTraces` fails when STAIRS precision on `traces/` is below `MIN_STAIRS_PRECISION = 0.9`, or when no trace is classified STAIRS. Points ride on STAIRS. With 3 real stairs traces, one false STAIRS drops precision to 0.75 or lower, so 0.9 fails CI on any false STAIRS. The workflow `.github/workflows/app.yml` runs it on every pull request that touches `app/`, `traces/`, `fixtures/` or `contracts/`. Checked by mutation at `9e0deca`: with the pressure-steps match removed from the stairs rule, both elevator rides became STAIRS, precision fell to 0.60 (3/5) and `realTraces` failed.

`fixtures/synthetic/` (24 generated files, 4 per label) is replayed too, but synthetic numbers are not evaluation: the data is generated, and `fixtures/synthetic/README.md` rules it out for evaluating, training or tuning thresholds. The test prints that matrix only to catch regressions, and the gate ignores it.

## Validation log

Each threshold change, with the evidence for it. A proposed change is not in the code until a later row marks it applied. Don't edit old rows.

| Date | Constant (file) | Old | New | Status | Evidence |
|---|---|---|---|---|---|
| 2026-11-02 | `MIN_STAIRS_PRECISION` (`TraceReplayTest.kt`) | none | 0.9 | Applied | New CI gate. One false STAIRS among 3 real stairs traces gives 0.75 or lower |
| 2026-11-02 | `MIN_ELEVATOR_SPEED_MPS` (`Classifier.kt`) | 1.0 | about 0.5 | Proposed, not applied | Both real rides: 0.693 m/s (`elevator_up_hand_20261026T083914Z`) and 0.586 m/s (`elevator_up_pocket_20261029T121310Z`), 0 steps. Not applied: 2 rides, one lift, one phone (SM-S918B), and elevator vs OTHER changes no points. Both speeds also sit inside the stairs speed band (0.1–0.9 m/s), so only steps separate the two. Re-check with rides in another lift and on the SM-G985F |
| 2026-11-02 | `MIN_ELEVATOR_SPEED_MPS` (`Classifier.kt`) | 1.0 | 0.5 (exclusive) | Applied in `d3e4951`, approved by Cristea on 2026-11-02 | The two real rides segment at 0.693 m/s (`elevator_up_hand_20261026T083914Z`) and 0.586 m/s (`elevator_up_pocket_20261029T121310Z`), 0 steps; both were OTHER at 1.0 and are ELEVATOR at 0.5. Still one lift and one phone |
