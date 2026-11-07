# Week 3 prompt (Ionut, Member B): segments, claim transaction, leaderboards

This file is the index. The binding spec is `Ionut/week3/spec.md`; every session has its own file `Ionut/week3/session_X.md`. Work is split into **six sessions** so the hard parts get the strongest model and the light parts get a cheap one.

## Sessions

| Session | Task | Model | Effort | Branch | Start |
|---|---|---|---|---|---|
| `w3-a` | Schema 0004, repository, claim transaction, scoring (critical path) | Opus 5.5 | high | `feat/w3-schema`, then `feat/w3-claim` | first |
| `w3-b` | Plausibility rules, `POST /v1/segments`, rate limits, batch service | Opus 5.5 | medium | `feat/w3-segments-api` | with A (part 1 needs no DB) |
| `w3-c` | Read endpoints, Valkey leaderboards | Sonnet 5.5 | medium | `feat/w3-read-api` | with A |
| `w3-d` | Fake segments, trace replay, end-to-end script | Sonnet 5.5 | high | `feat/w3-tools` | with A |
| `w3-e` | Docs, plan alignment, runbook | Sonnet 5.5 | low | `docs/w3-status` | any time |
| `w3-f` | Independent review (read-only, 3 reviewers) | Opus 5.5 | high | none | after A, B, C are merged |

Every session loads `token-saver` first, then the skills named in its file.

## Gates

- **G0**: this docs PR (spec, session files, contract 0.5.0-draft, fake_segments `device_id`) is merged to main. Nothing starts before it, because worktrees only see committed files.
- **G1**: A1 merged (tables and interfaces). B part 2 and C's database work start after it.
- **G2**: A, B, C, D merged and CI green, then `w3-f` reviews; findings become fix branches.
- **Wednesday check with Cristea**: deploy, run migration 0004, run seed, a real climb from the app, read-only SQL checks on the VM (Run command as postgres). VM actions are Ionut's only.

## Launch (one terminal per session, from the repo root, after G0)

```
claude -w w3-a -n w3-a --model opus --effort high "Read Ionut/week3/session_A.md and follow it."
claude -w w3-b -n w3-b --model opus --effort medium "Read Ionut/week3/session_B.md and follow it."
claude -w w3-c -n w3-c --model sonnet --effort medium "Read Ionut/week3/session_C.md and follow it."
claude -w w3-d -n w3-d --model sonnet --effort high "Read Ionut/week3/session_D.md and follow it."
claude -w w3-e -n w3-e --model sonnet --effort low "Read Ionut/week3/session_E.md and follow it."
claude -w w3-f -n w3-f --model opus --effort high "Read Ionut/week3/session_F.md and follow it."
```

The lead (this conversation, `w3-lead`) merges PRs when CI is green and relays messages if session messaging is unavailable. Resume a session with `claude -r w3-a`. If the environment variable `CLAUDE_CODE_EFFORT_LEVEL` is set it overrides `--effort`.

## Rules for all sessions (full list in spec section 11)

Branch per task, push, one PR per branch; no direct push to main; no trailers in commits or PRs; no secrets in output; no VM or Azure actions; stop your containers when done; report short (branch, commits, verify lines, decisions, open questions).

## Notice for Cristea

The sync worker must send `device_id` (the id from DeviceInfo used at sign-in) in each `POST /segments` batch. The contract adds the rejection reasons `started_at_range`, `season_inactive`, `no_team` and the response 403 `device-unknown`.
