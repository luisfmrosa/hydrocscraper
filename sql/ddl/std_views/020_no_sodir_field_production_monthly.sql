-- Std view: Sodir monthly field production, every Std file.
-- Business key: prfNpdidInformationCarrier, prfYear, prfMonth
-- Loaded into the Lake by sql/lake/no_sodir/field_production_monthly_{full,incremental}.sql.
--
-- Data columns: as written by sql/std/no_sodir/field_production_monthly.sql
-- (already typed), same names and order as the Lake table. Then the Std
-- metadata columns:
--   ___Std_md5             MD5 of the non-key columns, in this order, joined
--                          with chr(31); NULL becomes ''
--   ___Std_filename        full S3 path of the Std file
--   ___Std_year_month      year_month partition (the Raw file's)
--   ___Std_file_timestamp  download time (UTC) of the Raw file, from the
--                          file name suffix
--
-- CREATE OR REPLACE: the definition must follow the repository. Fails while
-- the dataset has no Std files yet; the app re-runs this script before every
-- Lake load.
CREATE OR REPLACE VIEW hook.std_views.no_sodir_field_production_monthly AS
SELECT
    prfNpdidInformationCarrier,
    prfYear,
    prfMonth,
    prfInformationCarrier,
    prfPrdOilNetMillSm3,
    prfPrdGasNetBillSm3,
    prfPrdNGLNetMillSm3,
    prfPrdCondensateNetMillSm3,
    prfPrdOeNetMillSm3,
    prfPrdProducedWaterInFieldMillSm3,
    md5(concat_ws(chr(31),
        coalesce(prfInformationCarrier::VARCHAR, ''),
        coalesce(prfPrdOilNetMillSm3::VARCHAR, ''),
        coalesce(prfPrdGasNetBillSm3::VARCHAR, ''),
        coalesce(prfPrdNGLNetMillSm3::VARCHAR, ''),
        coalesce(prfPrdCondensateNetMillSm3::VARCHAR, ''),
        coalesce(prfPrdOeNetMillSm3::VARCHAR, ''),
        coalesce(prfPrdProducedWaterInFieldMillSm3::VARCHAR, '')
    ))                                              AS ___Std_md5,
    filename                                        AS ___Std_filename,
    year_month::VARCHAR                             AS ___Std_year_month,
    strptime(regexp_extract(filename, '_(\d{8}_\d{4})\.[^./]+$', 1) || ' +0000',
             '%Y%m%d_%H%M %z')                      AS ___Std_file_timestamp
FROM read_parquet(
    's3://hydroc-std/no_sodir/field_production_monthly/*/*.parquet',
    hive_partitioning = true,
    filename = true,
    union_by_name = true
);
