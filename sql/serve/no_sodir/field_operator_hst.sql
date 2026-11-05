-- Serve: copies of the Library latest views of no_sodir_field_operator_hst into the Postgres
-- serving database (hydroc_serve, attached as serve), read by Metabase.
--   library.latest.no_sodir_field_operator_hst      -> serve.latest.no_sodir_field_operator_hst      (production)
--   library.latest.no_sodir_field_operator_hst_dev  -> serve.latest.no_sodir_field_operator_hst_dev  (development)
-- Run by storage/serve.py after every Lake load (and by --mode serve). A full
-- replace in one Postgres transaction: readers see the old copy or the new
-- one, never an empty or missing table. Read access for Metabase comes from
-- the schema's default privileges (set when the database was created).
BEGIN;
DROP TABLE IF EXISTS serve.latest.no_sodir_field_operator_hst;
CREATE TABLE serve.latest.no_sodir_field_operator_hst AS SELECT * FROM library.latest.no_sodir_field_operator_hst;
DROP TABLE IF EXISTS serve.latest.no_sodir_field_operator_hst_dev;
CREATE TABLE serve.latest.no_sodir_field_operator_hst_dev AS SELECT * FROM library.latest.no_sodir_field_operator_hst_dev;
COMMIT;
