# End-to-end check

Walks the Week 2 flow against a running server without a phone: sign-in code, sign in, teams, active season, join, QR check-in, refresh and reuse detection.

```powershell
.venv\Scripts\python.exe tools2e2e_check.py --email you@student.upt.ro --qr-token-file tools\qr\out.token.txt
```

It asks for the 6-digit code from the e-mail (hidden). Use your own address: it creates or updates a real account on the server. Nothing secret is printed.
