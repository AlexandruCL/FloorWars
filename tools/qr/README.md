# Entrance QR generator

Makes one signed QR code per building, to be printed and posted at the entrance. The token format
and its verification live in `server/app/qr_token.py` (`fwq1.<payload>.<signature>`, HMAC-SHA256).

## Usage

```bash
# The key: 64 hex characters, from SOPS (infra/secrets/auth.enc.env, FLOORWARS_QR_HMAC_KEY).
# Put it in a file outside the repo, or in the FLOORWARS_QR_HMAC_KEY environment variable.
# It is never accepted as a command-line value, so it stays out of shell history.

python tools/qr/make_entrance_qr.py --key-file ~/qr.key --out out \
    --building-id 1 --name "Building A" --building-id 2 --name "Building B"

# or all buildings in the database (FLOORWARS_DATABASE_URL)
python tools/qr/make_entrance_qr.py --key-file ~/qr.key --out out --from-db --days 7
```

Needs the `qrcode` package (`qrcode==8.2`) and, for `--from-db`, SQLAlchemy and psycopg (the
server virtualenv has them).

## Output

Per building, in `--out`:

- `<id>.svg`: the QR with the building name and the validity dates under it. Print this.
- `<id>.token.txt`: the token string embedded in the QR (used by the tests; handy for manual
  checks against the API). It is not secret on its own, but treat it like the printed code.

## Codes expire

A code is valid from the moment it is generated for `--days` days (default 7). After that the
check-in endpoint rejects it, so reprint before the date shown under the code. Rotating the key
invalidates all printed codes.

The tool never prints the key.
