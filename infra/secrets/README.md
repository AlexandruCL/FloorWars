# infra/secrets

SOPS + age encrypted secrets (plan 7.5). Only `*.enc.*` files and this README are tracked
(`infra/.gitignore`); any plaintext dropped here is ignored by git, but keep plaintext out of
the repo tree anyway. The age private key lives only on the VM (`/etc/floorwars/age.key`,
root, mode 0400) and in the team password manager. `.sops.yaml` holds the public key.

## Naming

`<name>.enc.<ext>` with `ext` one of `env`, `json`, `yaml`. `deploy.sh` decrypts every file into
`/run/secrets/floorwars/` (tmpfs, files mode 0400, owned by the container user that reads them):

| File type | Becomes |
|---|---|
| `<name>.enc.env` | One file per `KEY=value` line, named after the lower-cased key. Values unquoted, one line each. |
| `<name>.enc.json` / `.enc.yaml` | The whole document as `<name>.json` / `<name>.yaml` (for example a service-account key). |

Compose then mounts those files with `secrets:` into `/run/secrets/` inside the containers.

### API secret names carry the `floorwars_` prefix inside the container

The API reads settings with pydantic-settings, `env_prefix="FLOORWARS_"` and
`secrets_dir=/run/secrets`. pydantic-settings applies the prefix to secret file names too, so
the field `database_url` is read from **`/run/secrets/floorwars_database_url`**, not
`/run/secrets/database_url` (checked against the image). The host file keeps the short name;
the Compose `target` adds the prefix:

```yaml
secrets:
  - source: database_url          # /run/secrets/floorwars/database_url on the host
    target: floorwars_database_url # /run/secrets/floorwars_database_url in the api container
```

Postgres and Valkey read their own files (`postgres_password`, `valkey_password`) without a prefix.

## Needed secrets

| Secret (decrypted name) | Used by | Needed from | Notes |
|---|---|---|---|
| `database_url` | api (`floorwars_database_url`) | Week 1 | `postgresql+psycopg://postgres:<postgres_password>@postgres:5432/floorwars`; from Week 2 it uses the least-privilege app role `floorwars_app` (`postgresql+psycopg://floorwars_app:...`) |
| `postgres_password` | postgres (`POSTGRES_PASSWORD_FILE`) | Week 1 | Used only on first start (initdb); changing it later needs `ALTER ROLE` |
| `valkey_password` | valkey (`requirepass`) | Week 1 | Hex only (`openssl rand -hex 32`); it is written into a quoted config line |
| `valkey_url` | api (`floorwars_valkey_url`) | Week 1 | `redis://:<valkey_password>@valkey:6379/0` |
| `jwt_signing_key` | api (`floorwars_jwt_signing_key`) | Week 2 | In `auth.enc.env`. Hex of a 32-byte Ed25519 seed (64 hex characters, one line), **not a PEM**, so the `.enc.env` line split works. Rotated each semester (plan 7.5, 7.9); the previous public key goes in the non-secret setting `FLOORWARS_JWT_PREVIOUS_PUBLIC_KEYS` |
| `qr_hmac_key` | api (`floorwars_qr_hmac_key`) | Week 2 | In `auth.enc.env`. 32 random bytes, hex (64 characters) |
| `acs_access_key` | api (`floorwars_acs_access_key`) | Week 2 | In `acs.enc.env`. Azure Communication Services access key for the sign-in e-mails. The endpoint and the sender are not secret: `FLOORWARS_ACS_ENDPOINT` and `FLOORWARS_MAIL_FROM` in `infra/.env` |
| `migration_database_url` | `migrate` service (`floorwars_database_url`) | Week 2 | `postgresql+psycopg://floorwars_migrator:...`; DDL rights, created by `infra/sql/roles.sql` (plan 7.7) |

Week 2 auth secrets are in `auth.enc.env` (generated with Python's `secrets`, 32 bytes each):

```
jwt_signing_key=<64 hex characters>
qr_hmac_key=<64 hex characters>
```

Generate a replacement with `python -c "import secrets; print(secrets.token_hex(32))"` into a
plaintext file outside the repo, encrypt it as shown below, delete the plaintext. The API refuses
to start in `staging`/`prod` without `jwt_signing_key`; see `server/README.md` ("Configuration").

Week 1 suggestion: keep the four Week 1 values in one `app.enc.env`:

```
postgres_password=<hex>
valkey_password=<hex>
database_url=postgresql+psycopg://postgres:<postgres_password>@postgres:5432/floorwars
valkey_url=redis://:<valkey_password>@valkey:6379/0
```

`deploy.sh` refuses to deploy if any of `database_url`, `valkey_url`, `postgres_password`,
`valkey_password`, `jwt_signing_key`, `qr_hmac_key`, `acs_access_key`, `migration_database_url`
is missing after decryption (`REQUIRED_SECRETS`), with the message `missing secret <name>`.

## Encrypt and edit

Needs `sops` 3.9 or newer and `age`. Run from the repo root. `.sops.yaml` matches the
*target* path, so name it with `--filename-override` when the plaintext lives elsewhere:

```sh
# new secret file from a plaintext file outside the repo
sops --encrypt --filename-override infra/secrets/app.enc.env ~/tmp/app.env > infra/secrets/app.enc.env
sops --encrypt --filename-override infra/secrets/<name>.enc.json \
  ~/Downloads/<key>.json > infra/secrets/<name>.enc.json

# edit in place (opens $EDITOR on the decrypted content, re-encrypts on save)
sops infra/secrets/app.enc.env

# check: values must show as ENC[...]
git diff infra/secrets/
```

Then delete the plaintext (and empty the recycle bin). Never paste decrypted values into chats,
issues or CI logs.
