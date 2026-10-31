#!/usr/bin/env bash
# Create dummy secret files for the local stack (infra/compose.local.yml), plus a local
# infra/.env (API_TAG=local) when none exists, because docker-compose.yml requires API_TAG.
# Local development only: the values are random but never used outside this PC.
# infra/local-secrets/ and infra/.env are git-ignored. Existing files are kept unless --force.
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
infra_dir=$(cd "${script_dir}/.." && pwd)
out_dir="${infra_dir}/local-secrets"
force=false
[[ "${1:-}" == "--force" ]] && force=true

if [[ ! -f "${infra_dir}/.env" ]]; then
  printf '%s\n' "# Local dev only (written by make-local-secrets.sh). Not for the VM." \
    "API_TAG=local" "FLOORWARS_ENV=dev" "FLOORWARS_LOG_LEVEL=INFO" "FLOORWARS_MAIL_BACKEND=log" >"${infra_dir}/.env"
  echo "wrote infra/.env for local use"
fi

rand_hex() {
  # 32 hex chars; od is available in Git Bash, macOS and Linux.
  od -An -N16 -tx1 /dev/urandom | tr -d ' \n'
}

mkdir -p "$out_dir"
umask 077

# Each file is written on its own when missing, so an older local-secrets/ gains the newer
# files. --force regenerates only the postgres and valkey passwords (and the URLs built from them).
put_missing() { # put_missing <name> <value>
  [[ -f "$out_dir/$1" ]] || { printf '%s' "$2" >"$out_dir/$1"; echo "wrote $1"; }
}

if [[ -f "$out_dir/postgres_password" && "$force" == false ]]; then pg_pw=$(<"$out_dir/postgres_password"); else
  pg_pw=$(rand_hex); printf '%s' "$pg_pw" >"$out_dir/postgres_password"; fi
if [[ -f "$out_dir/valkey_password" && "$force" == false ]]; then vk_pw=$(<"$out_dir/valkey_password"); else
  vk_pw=$(rand_hex); printf '%s' "$vk_pw" >"$out_dir/valkey_password"; fi

pg_url="postgresql+psycopg://postgres:${pg_pw}@postgres:5432/floorwars"
if [[ "$force" == true ]]; then
  printf '%s' "$pg_url" >"$out_dir/database_url"
  printf '%s' "redis://:${vk_pw}@valkey:6379/0" >"$out_dir/valkey_url"
  printf '%s' "$pg_url" >"$out_dir/migration_database_url"
fi
put_missing database_url "$pg_url"
put_missing valkey_url "redis://:${vk_pw}@valkey:6379/0"
# Locally the app and the migrations both use the superuser (roles.sql is for the VM).
put_missing migration_database_url "$pg_url"
put_missing jwt_signing_key "$(rand_hex)$(rand_hex)"
put_missing qr_hmac_key "$(rand_hex)$(rand_hex)"
put_missing acs_access_key "local-placeholder-not-a-real-key"

echo "local secrets are in infra/local-secrets/"
echo "note: --force after a first run also needs 'docker compose ... down -v' (postgres keeps the old password)"
