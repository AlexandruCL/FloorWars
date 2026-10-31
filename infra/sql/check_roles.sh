#!/usr/bin/env bash
# Repeatable test of infra/sql/roles.sql against a throw-away PostGIS container.
#
#   docker run -d --rm --name fw-roles-db -e POSTGRES_PASSWORD=test -e POSTGRES_DB=floorwars \
#     -p 55455:5432 postgis/postgis:18-3.6
#   PYTHON=/path/to/python bash infra/sql/check_roles.sh        # then: docker stop fw-roles-db
#
# Applies the migrations as the superuser (like the first production deploy), runs roles.sql
# twice (idempotence), then checks that the app role cannot do DDL and the migrator can.
# Test passwords only; never run this against a real database.
set -euo pipefail

CONTAINER="${CONTAINER:-fw-roles-db}"
PORT="${PORT:-55455}"
PYTHON="${PYTHON:-python}"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
server_dir=$(cd "$here/../../server" && pwd)

SU_PW=test APP_PW=app-test-pw MIG_PW=mig-test-pw
url() { printf 'postgresql+psycopg://%s:%s@localhost:%s/floorwars' "$1" "$2" "$PORT"; }
psql_as() { # psql_as <user> <password> <sql>; prints nothing on success, returns psql status
  docker exec -e PGPASSWORD="$2" "$CONTAINER" psql -h localhost -U "$1" -d floorwars \
    -v ON_ERROR_STOP=1 -qtAc "$3"
}
fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "ok: $*"; }

for _ in $(seq 1 30); do
  docker exec "$CONTAINER" pg_isready -U postgres -d floorwars -h localhost >/dev/null 2>&1 && break
  sleep 2
done

echo "== migrations as superuser"
(cd "$server_dir" && FLOORWARS_DATABASE_URL="$(url postgres $SU_PW)" "$PYTHON" -m alembic upgrade head) >/dev/null

echo "== roles.sql (twice)"
for _ in 1 2; do
  docker exec -i "$CONTAINER" psql -U postgres -d floorwars -v ON_ERROR_STOP=1 -q \
    -v app_password="$APP_PW" -v migrator_password="$MIG_PW" <"$here/roles.sql" >/dev/null
done
ok "roles.sql applied twice"

echo "== app role"
psql_as floorwars_app $APP_PW "select count(*) from team" >/dev/null || fail "app cannot SELECT team"
ok "app SELECT on team"
psql_as floorwars_app $APP_PW "insert into team (code, color_hex) values ('roles-check', '#123456')" \
  >/dev/null || fail "app cannot INSERT into team (adjust the columns in this script if team changed)"
ok "app INSERT on team"
psql_as floorwars_app $APP_PW "delete from team where code = 'roles-check'" >/dev/null || fail "app cannot DELETE"
ok "app DELETE on team"
for ddl in "create table app_ddl_probe (id int)" "alter table team add column probe int" "drop table team"; do
  if out=$(psql_as floorwars_app $APP_PW "$ddl" 2>&1); then fail "app ran DDL: $ddl"; fi
  grep -qi "permission denied\|must be owner" <<<"$out" || fail "unexpected error for '$ddl': $out"
done
ok "app DDL denied (CREATE, ALTER, DROP)"
if psql_as floorwars_app $APP_PW "select * from alembic_version" >/dev/null 2>&1; then
  fail "app can read alembic_version"
fi
ok "app has no access to alembic_version"

echo "== migrator role"
psql_as floorwars_migrator $MIG_PW "create table mig_probe (id int generated always as identity primary key, n int)" >/dev/null \
  || fail "migrator cannot CREATE TABLE"
psql_as floorwars_app $APP_PW "insert into mig_probe (n) values (1)" >/dev/null \
  || fail "default privileges: app cannot INSERT into a migrator-created table"
psql_as floorwars_migrator $MIG_PW "drop table mig_probe" >/dev/null || fail "migrator cannot DROP"
ok "migrator DDL works and new tables get app grants"
(cd "$server_dir" && FLOORWARS_DATABASE_URL="$(url floorwars_migrator $MIG_PW)" "$PYTHON" -m alembic upgrade head) >/dev/null \
  || fail "alembic upgrade head as migrator"
ok "alembic upgrade head as migrator"
(cd "$server_dir" && FLOORWARS_DATABASE_URL="$(url floorwars_migrator $MIG_PW)" "$PYTHON" -m alembic check) >/dev/null \
  || fail "alembic check as migrator (drift)"
ok "alembic check as migrator (no drift)"

echo "ALL ROLE CHECKS PASSED"
