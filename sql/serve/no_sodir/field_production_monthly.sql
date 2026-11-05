-- Serve: copies of the Library latest views of no_sodir_field_production_monthly into the Postgres
-- serving database (hydroc_serve, attached as serve), read by Metabase.
--   library.latest.no_sodir_field_production_monthly      -> serve.latest.no_sodir_field_production_monthly      (production)
--   library.latest.no_sodir_field_production_monthly_dev  -> serve.latest.no_sodir_field_production_monthly_dev  (development)
-- Run by storage/serve.py after every Lake load (and by --mode serve). A full
-- replace in one Postgres transaction: readers see the old copy or the new
-- one, never an empty or missing table. Read access for Metabase comes from
-- the schema's default privileges (set when the database was created).
BEGIN;
DROP TABLE IF EXISTS serve.latest.no_sodir_field_production_monthly;
CREATE TABLE serve.latest.no_sodir_field_production_monthly AS SELECT * FROM library.latest.no_sodir_field_production_monthly;
DROP TABLE IF EXISTS serve.latest.no_sodir_field_production_monthly_dev;
CREATE TABLE serve.latest.no_sodir_field_production_monthly_dev AS SELECT * FROM library.latest.no_sodir_field_production_monthly_dev;
COMMIT;
