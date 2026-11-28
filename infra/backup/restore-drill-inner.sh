#!/bin/bash
# Runs INSIDE the throw-away container started by restore-drill.sh (as root; the pgBackRest
# and Postgres commands run as postgres). /drill is the scratch directory on the data disk.
set -euo pipefail

${CONF_CMD:-fw-pgbackrest-conf.sh}
install -d -o postgres -g postgres -m 0700 /drill/data
# shellcheck disable=SC2086  # RESTORE_ARGS is a list of options on purpose
su postgres -c "pgbackrest --stanza=floorwars --pg1-path=/drill/data $RESTORE_ARGS restore"
echo "restore of the files finished after ${SECONDS}s"

# No TCP port, socket in /tmp, archiving off (these flags are not part of the data directory).
su postgres -c "pg_ctl -D /drill/data -w -t 900 -l /drill/pg.log \
  -o '-c listen_addresses= -c unix_socket_directories=/tmp -c archive_mode=off -c shared_buffers=128MB' start"
sql() { su postgres -c "psql -h /tmp -U postgres -d floorwars -v ON_ERROR_STOP=1 -tA"; }
until [ "$(echo 'select pg_is_in_recovery()' | sql)" = "f" ]; do sleep 2; done
echo "WAL replay finished after ${SECONDS}s"

# Row count and a checksum of every row's text form, per key table. The live database keeps
# changing, so compare the counts with the live ones only roughly; the point is that they exist.
sql <<'SQL'
select 'user', count(*), md5(coalesce(string_agg(x::text, '|' order by x::text), '')) from "user" x;
select 'climb_segment', count(*), md5(coalesce(string_agg(x::text, '|' order by x::text), '')) from climb_segment x;
select 'team_building_score', count(*), md5(coalesce(string_agg(x::text, '|' order by x::text), '')) from team_building_score x;
select 'game_event', count(*), md5(coalesce(string_agg(x::text, '|' order by x::text), '')) from game_event x;
select 'newest user', max(created_at) from "user";
select 'newest game_event', max(created_at) from game_event;
SQL
su postgres -c "pg_ctl -D /drill/data -m fast stop"
echo "drill finished after ${SECONDS}s"
