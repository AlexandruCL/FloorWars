# End-to-end check

Walks the Week 2 flow against a running server without a phone: sign-in code, sign in, teams, active season, join, QR check-in, refresh and reuse detection.

```powershell
.venv\Scripts\python.exe tools\e2e\e2e_check.py --email you@student.upt.ro --qr-token-file tools\qr\out\1.token.txt
```

It asks for the 6-digit code from the e-mail (hidden). Use your own address: it creates or updates a real account on the server. Nothing secret is printed.

## `--upload` (Week 3)

```powershell
.venv\Scripts\python.exe tools\e2e\e2e_check.py --email you@student.upt.ro --qr-token-file tools\qr\out\1.token.txt --upload
```

Needs `--qr-token-file`, because the segments belong to the check-in. Right after the check-in it:

1. reads `GET /buildings/{id}/standings` (points before);
2. uploads a valid fake stairs segment with a fresh `Idempotency-Key` and expects it accepted with `points`;
3. uploads the same segment again (another fresh key) and expects it accepted without `points`;
4. uploads a `bad_ratio` segment and expects it rejected as `pressure_steps_mismatch`;
5. reads the standings again and shows each team's points before and after (the team that gained is yours, even if you joined it on an earlier run).

The fake segments come from `tools/fake_segments` and are synthetic test data, but the accepted one adds real points to your team in that building. Run it against the local test stack or the VM only on your own account.

Tests of the flow against an in-memory fake of the endpoints: `python -m pytest -q tools/e2e`.
