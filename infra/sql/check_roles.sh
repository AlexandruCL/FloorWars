#!/usr/bin/env bash
# Repeatable test of infra/sql/roles.sql against a throw-away PostGIS container.
#
#   docker run -d --rm --name fw-roles-db -e POSTGRES_PASSWORD=test -e POSTGRES_DB=floorwars \
#     -p 55455:5432 postgis/postgis:18-3.6
#   CONTAINER=fw-roles-db PYTHON=/path/to/python bash infra/sql/check_roles.sh   # then: docker stop fw-roles-db
#
# Case 1 (like the VM): migrations applied as the superuser first, then roles.sql (twice).
# Case 2 (fresh database): roles.sql first, then the migrator applies the migrations.
# Test passwords only; never run this against a real database.
set -euo pipefail

CONTAINER="${CONTAINER:-fw-roles-db}"
PORT="${PORT:-55455}"
PYTHON="${PYTHON:-python}"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
server_dir=$(cd "$here/../../server" && pwd)

SU_PW=test APP_PW=app-test-pw MIG_PW=mig-test-pw
url() { printf 'postgresql+psycopg://%s:%s@localhost:%s/%s' "$1" "$2" "$PORT" "$3"; } # user pw db
psql_as() { # psql_as <db> <user> <password> <sql>; returns psql's status, output on stdout
  docker exec -e PGPASSWORD="$3" "$CONTAINER" psql -h localhost -U "$2" -d "$1" \
    -v ON_ERROR_STOP=1 -qtAc "$4"
}
apply_roles() { # apply_roles <db>: passwords on stdin, exactly like the runbook
  { printf '\\set app_password %s\n\\set migrator_password %s\n' "$APP_PW" "$MIG_PW"
    cat "$here/roles.sql"; } |
    docker exec -i "$CONTAINER" psql -U postgres -d "$1" -v ON_ERROR_STOP=1 -q >/dev/null
}
alembic_as() { # alembic_as <db> <user> <password> <args...>
  local db=$1 user=$2 pw=$3
  shift 3
  (cd "$server_dir" && FLOORWARS_DATABASE_URL="$(url "$user" "$pw" "$db")" "$PYTHON" -m alembic "$@") >/dev/null
}
fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "ok: $*"; }
denied() { # denied <db> <label> <sql>: the app role must get permission denied / must be owner
  local out
  if out=$(psql_as "$1" floorwars_app $APP_PW "$3" 2>&1); then fail "app role could: $2"; fi
  grep -qi "permission denied\|must be owner\|must have\|permission to\|does not exist" <<<"$out" ||
    fail "unexpected error for '$2': $out"
}

for _ in $(seq 1 30); do
  docker exec "$CONTAINER" pg_isready -U postgres -d floorwars -h localhost >/dev/null 2>&1 && break
  sleep 2
done

echo "== case 1: migrations as superuser, then roles.sql (twice)"
alembic_as floorwars postgres $SU_PW upgrade head
apply_roles floorwars
apply_roles floorwars
ok "roles.sql applied twice (passwords via stdin)"

DB=floorwars
echo "== app role"
psql_as $DB floorwars_app $APP_PW "select count(*) from team" >/dev/null || fail "app cannot SELECT team"
ok "app SELECT on team"
psql_as $DB floorwars_app $APP_PW "insert into team (code, color_hex) values ('roles-check', '#123456')" \
  >/dev/null || fail "app cannot INSERT into team (adjust the columns if team changed)"
ok "app INSERT on team"
psql_as $DB floorwars_app $APP_PW "delete from team where code = 'roles-check'" >/dev/null || fail "app cannot DELETE"
ok "app DELETE on team"
denied $DB "CREATE TABLE" "create table app_ddl_probe (id int)"
denied $DB "ALTER TABLE" "alter table team add column probe int"
denied $DB "DROP TABLE" "drop table team"
ok "app DDL denied (CREATE, ALTER, DROP)"
denied $DB "CREATE TEMP TABLE" "create temp table tmp_probe (id int)"
ok "app cannot create temp tables"
denied $DB "read alembic_version" "select * from alembic_version"
ok "app has no access to alembic_version"
denied $DB "write spatial_ref_sys" "delete from spatial_ref_sys"
wr=$(psql_as $DB postgres $SU_PW "select count(*) from unnest(array['spatial_ref_sys','geometry_columns','geography_columns']) t, unnest(array['INSERT','UPDATE','DELETE']) p where has_table_privilege('floorwars_app', 'public.' || t, p)")
[[ "$wr" == "0" ]] || fail "app has write privileges on PostGIS catalogs ($wr)"
ok "PostGIS catalogs read-only for the app"
denied $DB "SET ROLE floorwars_migrator" "set role floorwars_migrator"
denied $DB "COPY TO PROGRAM" "copy (select 1) to program 'id'"
ok "app cannot SET ROLE or COPY ... TO PROGRAM"
members=$(psql_as $DB postgres $SU_PW "select count(*) from pg_auth_members m join pg_roles r on r.oid in (m.roleid, m.member) where r.rolname in ('floorwars_app','floorwars_migrator')")
[[ "$members" == "0" ]] || fail "roles are members of / have members ($members pg_auth_members rows)"
ok "no pg_auth_members rows for either role"
flags=$(psql_as $DB postgres $SU_PW "select count(*) from pg_roles where rolname in ('floorwars_app','floorwars_migrator') and not (rolsuper or rolcreatedb or rolcreaterole or rolreplication or rolbypassrls) and rolcanlogin")
[[ "$flags" == "2" ]] || fail "role attributes wrong (NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS expected)"
ok "role attributes: login only"

echo "== migrator role"
psql_as $DB floorwars_migrator $MIG_PW "create table mig_probe (id int generated always as identity primary key, n int)" >/dev/null \
  || fail "migrator cannot CREATE TABLE"
psql_as $DB floorwars_app $APP_PW "insert into mig_probe (n) values (1)" >/dev/null \
  || fail "default privileges: app cannot INSERT into a migrator-created table"
psql_as $DB floorwars_migrator $MIG_PW "create function mig_fn() returns int language sql as 'select 1'" >/dev/null \
  || fail "migrator cannot CREATE FUNCTION"
psql_as $DB floorwars_app $APP_PW "select mig_fn()" >/dev/null || fail "app cannot execute a migrator-created function"
psql_as $DB floorwars_migrator $MIG_PW "drop function mig_fn(); drop table mig_probe" >/dev/null || fail "migrator cannot DROP"
ok "migrator DDL works; new tables and functions get the app grants"
alembic_as $DB floorwars_migrator $MIG_PW upgrade head || fail "alembic upgrade head as migrator"
ok "alembic upgrade head as migrator"
alembic_as $DB floorwars_migrator $MIG_PW check || fail "alembic check as migrator (drift)"
ok "alembic check as migrator (no drift)"
psql_as postgres floorwars_app $APP_PW "select 1" >/dev/null 2>&1 && fail "app can connect to the postgres database"
ok "app cannot connect to the postgres database"

echo "== case 2: fresh database, roles.sql before the first migration"
DB=fresh_check
docker exec -e PGPASSWORD=$SU_PW "$CONTAINER" psql -h localhost -U postgres -d postgres -qc "drop database if exists $DB" >/dev/null
docker exec -e PGPASSWORD=$SU_PW "$CONTAINER" psql -h localhost -U postgres -d postgres -qc "create database $DB" >/dev/null
# extensions are a superuser step (the migrator has no CREATE on the database)
psql_as $DB postgres $SU_PW "create extension postgis; create extension citext" >/dev/null
apply_roles $DB
alembic_as $DB floorwars_migrator $MIG_PW upgrade head || fail "fresh: alembic upgrade head as migrator"
alembic_as $DB floorwars_migrator $MIG_PW check || fail "fresh: alembic check as migrator"
ok "fresh: migrator applies every revision, no drift"
psql_as $DB floorwars_app $APP_PW "select count(*) from team" >/dev/null || fail "fresh: app cannot SELECT team"
denied $DB "read alembic_version (fresh)" "select * from alembic_version"
owner=$(psql_as $DB postgres $SU_PW "select tableowner from pg_tables where tablename = 'alembic_version'")
[[ "$owner" == "floorwars_migrator" ]] || fail "fresh: alembic_version owner is $owner"
ok "fresh: app works on migrated tables and has no access to alembic_version"
docker exec -e PGPASSWORD=$SU_PW "$CONTAINER" psql -h localhost -U postgres -d postgres -qc "drop database $DB" >/dev/null

echo "ALL ROLE CHECKS PASSED"
