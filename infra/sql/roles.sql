-- FloorWars database roles (plan 7.7: the app role has no DDL, migrations use their own role).
--
-- Run ONCE per database by a person, as the postgres superuser, and again after any change to
-- this file (it is idempotent; re-running rotates the two passwords). The passwords are NOT
-- command-line arguments (they would show in `ps` and shell history) and not literals here:
-- the caller pipes two psql `\set` lines in front of this file on stdin, see
-- docs/runbook.md section 11:
--
--   { printf '\\set app_password %s\n\\set migrator_password %s\n' "$APP_PW" "$MIG_PW"
--     cat infra/sql/roles.sql; } | docker exec -i <postgres container> psql -U postgres \
--       -d floorwars -v ON_ERROR_STOP=1
--
--   floorwars_migrator  LOGIN, owns every schema object, may run DDL (alembic upgrade head).
--   floorwars_app       LOGIN, no DDL: SELECT/INSERT/UPDATE/DELETE on tables, USAGE on sequences.
--
-- Extensions: postgis and citext already exist from migration 0001. The migrator does NOT have
-- CREATE on the database, so every extension a later migration needs (for example btree_gist
-- for the check-in exclusion constraint) is created by hand as postgres BEFORE that migration:
--   CREATE EXTENSION IF NOT EXISTS btree_gist;
-- Trusted or not, the rule is the same: extensions are a superuser step.

-- Keep the passwords out of the server log, even when a statement fails.
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
-- No object in a schema the caller controls can shadow what this script calls.
SET search_path = pg_catalog, pg_temp;

\set ON_ERROR_STOP on

-- Roles (password set on every run, so re-running rotates it).
SELECT 'CREATE ROLE floorwars_migrator LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'floorwars_migrator') \gexec
SELECT 'CREATE ROLE floorwars_app LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'floorwars_app') \gexec

ALTER ROLE floorwars_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'migrator_password';
ALTER ROLE floorwars_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'app_password';

-- Database access: nobody by default, explicit CONNECT for the two roles (no TEMPORARY, no CREATE).
SELECT pg_catalog.format('REVOKE ALL ON DATABASE %I FROM PUBLIC', pg_catalog.current_database()) \gexec
SELECT pg_catalog.format('GRANT CONNECT ON DATABASE %I TO floorwars_app, floorwars_migrator',
                         pg_catalog.current_database()) \gexec
-- The maintenance databases are not for the app roles either (skipped when absent).
SELECT pg_catalog.format('REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC', datname)
FROM pg_catalog.pg_database WHERE datname IN ('postgres', 'template_postgis') \gexec
-- A superuser session in this database resolves unqualified names through pg_catalog first.
SELECT pg_catalog.format('ALTER ROLE postgres IN DATABASE %I SET search_path = pg_catalog, public',
                         pg_catalog.current_database()) \gexec

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO floorwars_app;
GRANT USAGE, CREATE ON SCHEMA public TO floorwars_migrator;

-- Alembic's bookkeeping table: created here when absent (a fresh database), owned by the
-- migrator, never visible to the app. Same definition Alembic itself creates.
CREATE TABLE IF NOT EXISTS public.alembic_version (
  version_num varchar(32) NOT NULL,
  CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- One-time: hand existing objects to the migrator. Tables, partitions, enum types and
-- sequences that are still owned by the superuser. Identity sequences follow their table.
-- PostGIS's own spatial_ref_sys stays with postgres.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname, c.relkind
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'S')
      AND c.relname <> 'spatial_ref_sys'
      AND pg_catalog.pg_get_userbyid(c.relowner) <> 'floorwars_migrator'
      AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.objid = c.oid AND d.deptype = 'i')
    ORDER BY c.relkind DESC, c.relname
  LOOP
    IF r.relkind = 'S' THEN
      EXECUTE pg_catalog.format('ALTER SEQUENCE public.%I OWNER TO floorwars_migrator', r.relname);
    ELSE
      EXECUTE pg_catalog.format('ALTER TABLE public.%I OWNER TO floorwars_migrator', r.relname);
    END IF;
  END LOOP;

  FOR r IN
    SELECT t.typname
    FROM pg_catalog.pg_type t
    JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typtype = 'e'
      AND pg_catalog.pg_get_userbyid(t.typowner) <> 'floorwars_migrator'
  LOOP
    EXECUTE pg_catalog.format('ALTER TYPE public.%I OWNER TO floorwars_migrator', r.typname);
  END LOOP;
END
$$;

-- The app: DML on every table, USAGE on every sequence; nothing on alembic_version, and the
-- PostGIS catalogs stay read-only.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO floorwars_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO floorwars_app;
REVOKE INSERT, UPDATE, DELETE ON public.spatial_ref_sys, public.geometry_columns,
  public.geography_columns FROM floorwars_app;
DO $$
BEGIN
  IF pg_catalog.to_regclass('public.alembic_version') IS NOT NULL THEN
    REVOKE ALL ON public.alembic_version FROM floorwars_app;
  END IF;
END
$$;

-- Future objects created by the migrator: the app gets DML and sequence USAGE automatically;
-- functions are not executable by PUBLIC (only the app role and the owner).
ALTER DEFAULT PRIVILEGES FOR ROLE floorwars_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO floorwars_app;
ALTER DEFAULT PRIVILEGES FOR ROLE floorwars_migrator IN SCHEMA public
  GRANT USAGE ON SEQUENCES TO floorwars_app;
ALTER DEFAULT PRIVILEGES FOR ROLE floorwars_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE floorwars_migrator IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO floorwars_app;
