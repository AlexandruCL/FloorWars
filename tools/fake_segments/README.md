# Fake segments

Posts fake climb segments to `POST /segments` with no phone (plan section 9.2). Ionut uses it to test the server; Cristea uses it against the Prism mock (`contracts/prism/README.md`). Python 3.11 or later, standard library only.

The segments follow the `Segment` schema in `contracts/openapi.yaml` (0.2.0-draft) and stay inside its bounds, so a server rejects the bad kinds item by item, never with 422.

| `--kind` | What it makes | Expected server result |
|---|---|---|
| `stairs` (default) | ascent 2.0 to 30 m, 5 to 7 steps per metre, 0.2 to 0.7 m/s, 5 s to 3 min, step rate at most 3 per second, `stair_prob` 0.8 to 0.99 | accepted and scored |
| `elevator` | above 1.0 m/s, fewer than 1 step per metre | rejected (`speed` or `pressure_steps_mismatch`) |
| `shake` | ascent 2.0 to 2.6 m with 20 to 60 steps per metre | rejected (`pressure_steps_mismatch`) |
| `mixed` | about 60% stairs, 20% elevator, 20% shake | both |

These are synthetic test data, never real climbs.

## Usage

```sh
# Against Prism on the default port (no /v1 on the mock)
python tools/fake_segments/fake_segments.py --count 5 --batch-size 5

# Same batch sent twice with the same Idempotency-Key
python tools/fake_segments/fake_segments.py --count 5 --batch-size 5 --repeat-last

# Print the batches as JSON and send nothing
python tools/fake_segments/fake_segments.py --dry-run --count 3 --seed 1

# Against a real server: its /v1 base, a real token, the check-in's id and building
set FLOORWARS_TOKEN=<access token>          # PowerShell: $env:FLOORWARS_TOKEN = "..."
python tools/fake_segments/fake_segments.py --base-url http://127.0.0.1:8000/v1 \
  --checkin-id <uuid> --building-id 4 --kind mixed --count 20 --start now
```

| Option | Default | Meaning |
|---|---|---|
| `--base-url` | `http://127.0.0.1:4010` | API base. The mock has no `/v1`; a real server does |
| `--token` | `$FLOORWARS_TOKEN`, else a dummy | Bearer token. Never printed |
| `--building-id` | `1` | Building of the check-in |
| `--checkin-id` | random UUID | Check-in the segments belong to |
| `--count` | `5` | Segments to generate |
| `--batch-size` | `10` | Segments per request, 1 to 100 (the contract's limit) |
| `--seed` | none | Makes ids, keys, values and times repeat |
| `--kind` | `stairs` | `stairs`, `elevator`, `shake` or `mixed` |
| `--start` | now; with `--seed`, `2026-11-02T10:00:00Z` | First `started_at` (ISO time or `now`). Later segments follow in time order |
| `--dry-run` | off | Print `{"batches": [{"idempotency_key", "body"}]}` and send nothing |
| `--repeat-last` | off | After sending, resend the last batch with the same `Idempotency-Key` |

Each batch gets a new UUID `Idempotency-Key`. Timeouts: connect 10 s, read 20 s. One line is printed per batch:

```
batch 1/1 status=200 accepted=4 rejected=1 flips=0 reasons=pressure_steps_mismatch key=...
```

Exit code 0 on success, 1 on an HTTP error status, 2 on a connection error or bad arguments.

A seeded run repeats its ids and keys, so sending it twice to a real server tests idempotency too. Pass `--start now` (or a time inside the check-in) when the server checks that a check-in is valid at `started_at`; the fixed seeded start would be rejected with `no_checkin`.

## Tests

```sh
python -m pytest -q tools/fake_segments
```

They check that stairs pass the scoring rule and elevator and shake fail it, that every segment and batch validates against the contract (with `jsonschema` when installed, plus a small built-in bounds check), seed determinism and the dry-run output.

The thresholds here mirror plan section 3.3 for test data only. The server's config is the authority.
