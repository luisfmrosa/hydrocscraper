#!/bin/sh
# Serving layer (Metabase), the Docker counterpart of the Incus postgres role:
#   hydroc_serve  owned by user_hydroc_serve (the DuckDB server writes the
#                 copies of the Library latest views into schema latest)
#   metabase      Metabase's application database, owned by user_metabase,
#                 who may only read hydroc_serve.latest
# Run by the one-shot postgres-serve-init service on every `docker compose up`
# (PGHOST/PGUSER/PGPASSWORD from compose.yaml), on new and existing volumes
# alike, so it must stay idempotent.
set -eu

: "${PG_PASSWORD_SERVE:?}" "${PG_PASSWORD_METABASE:?}"

psql -v ON_ERROR_STOP=1 --dbname postgres \
    -v pw_serve="$PG_PASSWORD_SERVE" -v pw_mb="$PG_PASSWORD_METABASE" <<'SQL'
SELECT format('CREATE USER %I', u)
FROM unnest(ARRAY['user_hydroc_serve', 'user_metabase']) AS u
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = u) \gexec
ALTER USER user_hydroc_serve WITH PASSWORD :'pw_serve';
ALTER USER user_metabase WITH PASSWORD :'pw_mb';

SELECT format('CREATE DATABASE %I OWNER %I', d, o)
FROM (VALUES ('hydroc_serve', 'user_hydroc_serve'), ('metabase', 'user_metabase')) AS t(d, o)
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = d) \gexec
SQL

psql -v ON_ERROR_STOP=1 --dbname hydroc_serve <<'SQL'
CREATE SCHEMA IF NOT EXISTS latest AUTHORIZATION user_hydroc_serve;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA latest TO user_metabase;
-- The serve scripts drop and recreate every table: grant on future tables
ALTER DEFAULT PRIVILEGES FOR ROLE user_hydroc_serve IN SCHEMA latest
    GRANT SELECT ON TABLES TO user_metabase;
GRANT SELECT ON ALL TABLES IN SCHEMA latest TO user_metabase;
SQL
