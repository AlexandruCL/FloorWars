#!/usr/bin/env bash
# FloorWars deploy and rollback (plan 7.5, 7.6). Runs as root on the VM.
#
#   deploy.sh <40-hex git sha>   deploy the GHCR image tagged with that sha
#   deploy.sh rollback           re-pin the tag recorded in /srv/floorwars/last_good
#
# As an SSH forced command (deploy user, see docs/runbook.md) the request is read from
# SSH_ORIGINAL_COMMAND, e.g. `ssh deploy@<VM_IP> <sha>`. Only a 40-hex sha or `rollback`
# is accepted; anything else is refused.
#
# Steps for a deploy: lock; check out <sha> (must be on origin/main) in the repo clone;
# decrypt infra/secrets/*.enc.* with SOPS + age into SECRETS_DIR (tmpfs, files mode 0400);
# pull images; start postgres/valkey; run expand-only migrations; `docker compose up -d
# --wait`; on failure within HEALTH_TIMEOUT seconds re-pin the previous tag automatically.
# Rollbacks never run migrations (expand-only migrations keep the old image working).
#
# The whole script is inside main() so bash has parsed all of it before `git checkout`
# replaces this file on disk.

set -euo pipefail

main() {
  readonly ROOT="${FLOORWARS_ROOT:-/srv/floorwars}"           # encrypted data disk mount
  readonly REPO_DIR="${FLOORWARS_REPO_DIR:-$ROOT/repo}"        # git clone of this repo
  readonly INFRA_DIR="$REPO_DIR/infra"
  readonly LAST_GOOD_FILE="$ROOT/last_good"                    # tag to roll back to
  readonly CURRENT_FILE="$ROOT/current"                        # tag running now
  readonly LOG_FILE="$ROOT/deploy.log"
  readonly LOCK_FILE="/run/lock/floorwars-deploy.lock"
  readonly HEALTH_TIMEOUT="${FLOORWARS_HEALTH_TIMEOUT:-90}"
  export DATA_DIR="${DATA_DIR:-$ROOT/data}"
  export SECRETS_DIR="${SECRETS_DIR:-/run/secrets/floorwars}"
  export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-/etc/floorwars/age.key}"
  # Keep in sync with the top-level `secrets:` in docker-compose.yml.
  readonly REQUIRED_SECRETS=(database_url valkey_url postgres_password valkey_password
    jwt_signing_key qr_hmac_key acs_access_key migration_database_url)

  local request
  request=$(parse_request "$@")

  [[ $EUID -eq 0 ]] || die "must run as root (the deploy user calls it through sudo)"
  [[ -d "$REPO_DIR/.git" ]] || die "no git clone at $REPO_DIR"
  # Never start postgres on the OS disk by accident (data disk not mounted after a reboot).
  mountpoint -q "$ROOT" || die "$ROOT is not a mount point; is the data disk mounted?"

  exec 9>"$LOCK_FILE"
  flock -n 9 || die "another deploy is running"
  exec > >(tee -a "$LOG_FILE") 2>&1

  local current last_good
  current=$(read_tag "$CURRENT_FILE")
  last_good=$(read_tag "$LAST_GOOD_FILE")
  log "request=$request current=${current:-none} last_good=${last_good:-none}"

  if [[ "$request" == "rollback" ]]; then
    [[ -n "$last_good" ]] || die "nothing to roll back to: $LAST_GOOD_FILE is empty"
    if release "$last_good" no-migrate; then
      write_tag "$CURRENT_FILE" "$last_good"
      log "rollback to $last_good done"
      return 0
    fi
    die "rollback to $last_good failed; inspect with: docker compose ps / logs"
  fi

  local sha="$request"
  # Record the running tag before touching anything; it is what a failure re-pins.
  if [[ -n "$current" && "$current" != "$sha" ]]; then
    write_tag "$LAST_GOOD_FILE" "$current"
    last_good="$current"
  fi

  if release "$sha" migrate; then
    write_tag "$CURRENT_FILE" "$sha"
    log "deploy of $sha done"
    return 0
  fi

  log "deploy of $sha failed"
  if [[ -z "$last_good" || "$last_good" == "$sha" ]]; then
    die "no previous tag to re-pin; the stack may be down"
  fi
  log "re-pinning previous tag $last_good"
  if release "$last_good" no-migrate; then
    write_tag "$CURRENT_FILE" "$last_good"
    log "re-pinned $last_good; deploy of $sha FAILED"
    exit 1
  fi
  log "ERROR: re-pin of $last_good also failed; manual action needed (docs/runbook.md)"
  exit 2
}

usage() {
  echo "usage: deploy.sh <40-hex git sha> | deploy.sh rollback" >&2
  exit 64
}

log() { printf '%s deploy: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die() {
  log "ERROR: $*"
  exit 1
}

# Prints the validated request. SSH_ORIGINAL_COMMAND wins when set (forced command).
parse_request() {
  local req
  if [[ -n "${SSH_ORIGINAL_COMMAND:-}" ]]; then
    [[ $# -eq 0 ]] || usage
    req="$SSH_ORIGINAL_COMMAND"
  else
    [[ $# -eq 1 ]] || usage
    req="$1"
  fi
  if [[ "$req" =~ ^[0-9a-f]{40}$ || "$req" == "rollback" ]]; then
    printf '%s\n' "$req"
  else
    usage
  fi
}

read_tag() {
  local tag=""
  [[ -f "$1" ]] && tag=$(head -n1 "$1")
  if [[ -n "$tag" && ! "$tag" =~ ^[0-9a-f]{40}$ ]]; then
    die "corrupt tag in $1"
  fi
  printf '%s' "$tag"
}

write_tag() {
  printf '%s\n' "$2" >"$1.tmp"
  mv -f "$1.tmp" "$1"
}

compose() {
  docker compose --project-directory "$INFRA_DIR" -f "$INFRA_DIR/docker-compose.yml" "$@"
}

# release <sha> <migrate|no-migrate>: check out, decrypt, pull, (migrate), up --wait.
release() {
  local sha="$1" mode="$2"
  log "release $sha ($mode)"
  checkout "$sha" || return 1
  [[ -f "$INFRA_DIR/.env" ]] || { log "missing $INFRA_DIR/.env (copy .env.example)"; return 1; }
  decrypt_secrets || return 1

  export API_TAG="$sha"
  # the postgres image (uid 999) must be able to traverse its bind-mounted parent dir
  install -d -m 0700 -o 999 -g 999 "$DATA_DIR/postgres"
  compose pull --quiet || { log "image pull failed (is root logged in to ghcr.io?)"; return 1; }
  compose up -d --wait --wait-timeout "$HEALTH_TIMEOUT" postgres valkey || return 1

  if [[ "$mode" == "migrate" ]]; then
    # Expand-only migrations (plan 7.7). Skipped while the image has no alembic.ini yet.
    # Runs as the `migrate` service: same image, but with the migration role's database URL.
    compose --profile tools run --rm --no-deps -T migrate sh -c \
      'if [ -f alembic.ini ]; then exec alembic upgrade head; else echo "no alembic.ini, skipping migrations"; fi' ||
      { log "migrations failed; the running api was not touched"; return 1; }
  fi

  compose up -d --remove-orphans --wait --wait-timeout "$HEALTH_TIMEOUT" || {
    log "services not healthy within ${HEALTH_TIMEOUT}s"
    compose ps >&2 || true
    return 1
  }
}

checkout() {
  local sha="$1"
  git -C "$REPO_DIR" fetch --quiet origin main || { log "git fetch failed"; return 1; }
  git -C "$REPO_DIR" cat-file -e "${sha}^{commit}" 2>/dev/null || { log "unknown commit $sha"; return 1; }
  git -C "$REPO_DIR" merge-base --is-ancestor "$sha" origin/main ||
    { log "$sha is not on origin/main; refusing"; return 1; }
  git -C "$REPO_DIR" checkout --quiet --force --detach "$sha"
}

# Owner of each decrypted secret file inside SECRETS_DIR (files are bind-mounted as is).
secret_owner() {
  case "$1" in
    postgres_password | valkey_password) echo "999:999" ;; # postgres / valkey image users
    *) echo "10001:10001" ;;                               # api (and later worker) image user
  esac
}

# Note: release() and everything it calls run inside `if`/`||`, where bash ignores
# `set -e`, so every step below checks its own status.

write_secret() {
  local dir="$1" name="$2" value="$3"
  (umask 077 && printf '%s' "$value" >"$dir/$name") || return 1
  chown "$(secret_owner "$name")" "$dir/$name" || return 1
  chmod 0400 "$dir/$name"
}

# Decrypts every infra/secrets/<name>.enc.<ext> into a fresh directory, then swaps it in.
decrypt_secrets() {
  local parent fstype staging
  [[ -r "$SOPS_AGE_KEY_FILE" ]] || { log "age key $SOPS_AGE_KEY_FILE not readable"; return 1; }
  parent=$(dirname "$SECRETS_DIR")
  install -d -m 0700 "$parent" || return 1
  fstype=$(stat -f -c %T "$parent") || return 1
  [[ "$fstype" == "tmpfs" ]] || { log "$parent is $fstype, not tmpfs; refusing to write secrets"; return 1; }

  staging=$(mktemp -d "$parent/.floorwars.XXXXXX") || return 1
  [[ -n "$staging" && -d "$staging" ]] || return 1
  if ! fill_secrets "$staging"; then
    rm -rf "$staging"
    return 1
  fi

  # Running containers keep their bind-mounted files; new ones get the new set.
  rm -rf "$SECRETS_DIR.old" || return 1
  if [[ -d "$SECRETS_DIR" ]]; then
    mv "$SECRETS_DIR" "$SECRETS_DIR.old" || return 1
  fi
  mv "$staging" "$SECRETS_DIR" || return 1
  rm -rf "$SECRETS_DIR.old"
  log "secrets decrypted into $SECRETS_DIR"
}

#   .enc.env         one file per KEY=value line, named after the lower-cased key
#   .enc.json/.yaml  the whole decrypted document as <name>.json / <name>.yaml
fill_secrets() {
  local dir="$1" f base name ext plain line key value s
  local files=()
  shopt -s nullglob
  files=("$INFRA_DIR"/secrets/*.enc.*)
  shopt -u nullglob
  [[ ${#files[@]} -gt 0 ]] || { log "no encrypted secrets in $INFRA_DIR/secrets"; return 1; }

  for f in "${files[@]}"; do
    base=${f##*/}
    name=${base%%.enc.*}
    ext=${base##*.enc.}
    plain=$(sops --decrypt "$f") || { log "sops could not decrypt $base"; return 1; }
    case "$ext" in
      env)
        while IFS= read -r line || [[ -n "$line" ]]; do
          [[ -z "$line" || "$line" == \#* ]] && continue
          key=${line%%=*}
          value=${line#*=}
          key=${key,,}
          [[ "$key" =~ ^[a-z0-9_]+$ ]] || { log "invalid key name in $base"; return 1; }
          write_secret "$dir" "$key" "$value" || return 1
        done <<<"$plain"
        ;;
      json | yaml)
        write_secret "$dir" "$name.$ext" "$plain" || return 1
        ;;
      *)
        log "unsupported secret file type: $base"
        return 1
        ;;
    esac
  done

  for s in "${REQUIRED_SECRETS[@]}"; do
    [[ -s "$dir/$s" ]] || { log "missing secret $s (required; see infra/secrets/README.md)"; return 1; }
  done
}

main "$@"
exit
