-- Raw view: NPD monthly field production, every file in Raw, as received.
-- Read by sql/std/npd/field_production_monthly.sql (one file at a time).
--
-- Data columns: every source column, named as in the file, as text
-- (all_varchar): typing and checks happen in the Std script. Then the Raw
-- metadata columns:
--   ___Raw_filename        full S3 path of the source file
--   ___Raw_year_month      year_month partition of the file
--   ___Raw_file_timestamp  download time (UTC) from the file name suffix
--
-- CREATE OR REPLACE: the definition must follow the repository. Fails while
-- the dataset has no files yet (no files to bind); the app re-runs this
-- script before every Std step.
CREATE OR REPLACE VIEW hook.raw_views.npd_field_production_monthly AS
SELECT
    prfInformationCarrier,
    prfYear,
    prfMonth,
    prfPrdOilNetMillSm3,
    prfPrdGasNetBillSm3,
    prfPrdNGLNetMillSm3,
    prfPrdCondensateNetMillSm3,
    prfPrdOeNetMillSm3,
    prfPrdProducedWaterInFieldMillSm3,
    prfNpdidInformationCarrier,
    filename                                        AS ___Raw_filename,
    year_month::VARCHAR                             AS ___Raw_year_month,
    strptime(regexp_extract(filename, '_(\d{8}_\d{4})\.[^./]+$', 1) || ' +0000',
             '%Y%m%d_%H%M %z')                      AS ___Raw_file_timestamp
FROM read_csv(
    's3://hydroc-raw/npd/field_production_monthly/*/*.csv',
    hive_partitioning = true,
    filename = true,
    union_by_name = true,
    all_varchar = true
);
