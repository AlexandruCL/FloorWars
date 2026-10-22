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
    "API_TAG=local" "FLOORWARS_ENV=dev" "FLOORWARS_LOG_LEVEL=INFO" >"${infra_dir}/.env"
  echo "wrote infra/.env for local use"
fi

rand_hex() {
  # 32 hex chars; od is available in Git Bash, macOS and Linux.
  od -An -N16 -tx1 /dev/urandom | tr -d ' \n'
}

mkdir -p "$out_dir"
umask 077

if [[ -f "$out_dir/postgres_password" && "$force" == false ]]; then
  echo "local secrets already exist in infra/local-secrets (use --force to regenerate)"
  exit 0
fi

pg_pw=$(rand_hex)
vk_pw=$(rand_hex)

printf '%s' "$pg_pw" >"$out_dir/postgres_password"
printf '%s' "$vk_pw" >"$out_dir/valkey_password"
printf '%s' "postgresql+psycopg://postgres:${pg_pw}@postgres:5432/floorwars" >"$out_dir/database_url"
printf '%s' "redis://:${vk_pw}@valkey:6379/0" >"$out_dir/valkey_url"

echo "wrote dummy secrets to infra/local-secrets/"
echo "note: --force after a first run also needs 'docker compose ... down -v' (postgres keeps the old password)"
