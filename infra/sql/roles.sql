-- FloorWars database roles (plan 7.7: the app role has no DDL, migrations use their own role).
--
-- Run ONCE per database by a person, as the postgres superuser, and again after any change to
-- this file (it is idempotent). Passwords are psql variables, never literals in this file:
--
--   docker exec -i floorwars-postgres-1 psql -U postgres -d floorwars -v ON_ERROR_STOP=1 \
--     -v app_password="$APP_PW" -v migrator_password="$MIG_PW" < infra/sql/roles.sql
--
-- (generate the two passwords with openssl rand -hex 24 and keep them: they go into the SOPS
-- URLs, see docs/runbook.md section 11.)
--
--   floorwars_migrator  LOGIN, owns every schema object, may run DDL (alembic upgrade head).
--   floorwars_app       LOGIN, no DDL: SELECT/INSERT/UPDATE/DELETE on tables, USAGE on sequences.
--
-- Extensions: postgis and citext already exist from migration 0001. CREATE EXTENSION for
-- postgis needs a superuser, so a future migration that adds a NON-trusted extension must be
-- pre-created by hand as postgres. Trusted extensions (btree_gist, citext, pg_trgm, ...) can be
-- created by floorwars_migrator because it has CREATE on the database.

\set ON_ERROR_STOP on

-- Roles (password set on every run, so re-running rotates it).
SELECT 'CREATE ROLE floorwars_migrator LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'floorwars_migrator') \gexec
SELECT 'CREATE ROLE floorwars_app LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'floorwars_app') \gexec

ALTER ROLE floorwars_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'migrator_password';
ALTER ROLE floorwars_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';

-- Database and schema access.
SELECT format('GRANT CONNECT ON DATABASE %I TO floorwars_app', current_database()) \gexec
SELECT format('GRANT CONNECT, CREATE ON DATABASE %I TO floorwars_migrator', current_database()) \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO floorwars_app;
GRANT USAGE, CREATE ON SCHEMA public TO floorwars_migrator;

-- One-time: hand existing objects to the migrator. Tables, partitions, enum types and
-- sequences that are still owned by the superuser. Identity sequences follow their table.
-- PostGIS's own spatial_ref_sys stays with postgres.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname, c.relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'S')
      AND c.relname <> 'spatial_ref_sys'
      AND pg_get_userbyid(c.relowner) <> 'floorwars_migrator'
      AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'i')
    ORDER BY c.relkind DESC, c.relname
  LOOP
    IF r.relkind = 'S' THEN
      EXECUTE format('ALTER SEQUENCE public.%I OWNER TO floorwars_migrator', r.relname);
    ELSE
      EXECUTE format('ALTER TABLE public.%I OWNER TO floorwars_migrator', r.relname);
    END IF;
  END LOOP;

  FOR r IN
    SELECT t.typname
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typtype = 'e'
      AND pg_get_userbyid(t.typowner) <> 'floorwars_migrator'
  LOOP
    EXECUTE format('ALTER TYPE public.%I OWNER TO floorwars_migrator', r.typname);
  END LOOP;
END
$$;

-- The app: DML on every table, USAGE on every sequence; nothing on alembic_version.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO floorwars_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO floorwars_app;
REVOKE INSERT, UPDATE, DELETE ON public.spatial_ref_sys FROM floorwars_app; -- read-only PostGIS data
REVOKE ALL ON public.alembic_version FROM floorwars_app;

-- Future objects created by the migrator get the app grants automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE floorwars_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO floorwars_app;
ALTER DEFAULT PRIVILEGES FOR ROLE floorwars_migrator IN SCHEMA public
  GRANT USAGE ON SEQUENCES TO floorwars_app;
