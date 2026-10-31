# Entrance QR generator

Makes one signed QR code per building, to be printed and posted at the entrance. The token format
and its verification live in `server/app/qr_token.py` (`fwq1.<payload>.<signature>`, HMAC-SHA256).

## Usage

```bash
# The key: 64 hex characters, from SOPS (infra/secrets/auth.enc.env, FLOORWARS_QR_HMAC_KEY).
# Put it in a file outside the repo, or in the FLOORWARS_QR_HMAC_KEY environment variable.
# It is never accepted as a command-line value, so it stays out of shell history.

python tools/qr/make_entrance_qr.py --key-file ~/qr.key --out tools/qr/out \
    --building-id 1 --name "Building A" --building-id 2 --name "Building B"

# PowerShell: write the key file without BOM and newline
#   Set-Content -NoNewline -Encoding ascii qr.key '<64 hex characters>'

# or all buildings in the database (FLOORWARS_DATABASE_URL)
python tools/qr/make_entrance_qr.py --key-file ~/qr.key --out tools/qr/out --from-db --days 7
```

Needs the `qrcode` package (`qrcode==8.2`) and, for `--from-db`, SQLAlchemy and psycopg (the
server virtualenv has them).

## Output

Per building, in `--out`:

- `<id>.svg`: the QR with the building name and the validity dates under it. Print this.
- `<id>.token.txt`: the token string embedded in the QR (used by the tests; handy for manual
  checks against the API). It is not secret on its own, but treat it like the printed code.

## Security notes

- A printed code is a bearer token: anyone holding a photo of it can present it from anywhere
  until `exp`. QR check-ins are therefore only as strong as the validity window (default 7 days,
  at most 31). The check-in API adds its own plausibility checks on top.
- `.token.txt` files contain the same token as the QR. Never commit them. `.gitignore` excludes
  `tools/qr/out/` and `*.token.txt`; use `--out tools/qr/out` or a folder outside the repo.
- `nbf` is set 5 minutes before the start date shown on the code, to allow for clock skew.

## Codes expire

A code is valid from the moment it is generated for `--days` days (default 7). After that the
check-in endpoint rejects it, so reprint before the date shown under the code. Rotating the key
invalidates all printed codes.

The tool never prints the key.
