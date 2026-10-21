# Synthetic traces

Generated test data, not real recordings. Do not use these for evaluation or to train or tune thresholds.

- Made by `tools/synthetic_traces/generate.py` (Python stdlib, fixed seed). Rerun it to regenerate the same bytes.
- Same CSV format as the sensor logger export (T4), plus `# synthetic,true`, `# generator`, `# seed` and `# device_model,SYNTHETIC` in every file.
- 24 files covering all six labels and all three placements. `labels.csv` has one row per file; `device` is `SYNTHETIC` and `floor_range` is `n/a`.
- They do not count toward the T5 done-when criteria. Real labelled recordings from the two test phones go in `/traces`.

What the generator models, roughly: pressure at about 50 Hz for 30 s (about 0.12 hPa per metre, 3.5 m floors), step events for stairs and walking, stair flights with landings, a smooth elevator ramp, extra noise for `shake`, and short pressure bumps for `blow`.
