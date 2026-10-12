-- Std view: Sodir company reserves, every Std file.
-- Business key: fldNpdidField, cmpNpdidCompany
-- Loaded into the Lake by sql/lake/no_sodir/company_reserves_{full,incremental}.sql.
--
-- Data columns: as written by sql/std/no_sodir/company_reserves.sql (already typed),
-- same names and order as the Lake table. Then the Std metadata columns:
--   ___Std_md5             MD5 of the non-key columns, in this order, joined
--                          with chr(31); NULL becomes ''. Leaves out
--                          DatesyncNPD: Sodir moves it with every export, so it
--                          would make a new version of every row each day
--   ___Std_filename        full S3 path of the Std file
--   ___Std_year_month      year_month partition (the Raw file's)
--   ___Std_file_timestamp  download time (UTC) of the Raw file, from the
--                          file name suffix
--
-- CREATE OR REPLACE: the definition must follow the repository. Fails while
-- the dataset has no Std files yet; the app re-runs this script before every
-- Lake load.
CREATE OR REPLACE VIEW hook.std_views.no_sodir_company_reserves AS
SELECT
    fldNpdidField,
    cmpNpdidCompany,
    cmpLongName,
    fldName,
    cmpRemainingOil,
    cmpRemainingGas,
    cmpRemainingNGL,
    cmpRemainingCondensate,
    cmpRemainingOE,
    cmpDateOffResEstDisplay,
    cmpShare,
    DatesyncNPD,
    md5(concat_ws(chr(31),
        coalesce(cmpLongName::VARCHAR, ''),
        coalesce(fldName::VARCHAR, ''),
        coalesce(cmpRemainingOil::VARCHAR, ''),
        coalesce(cmpRemainingGas::VARCHAR, ''),
        coalesce(cmpRemainingNGL::VARCHAR, ''),
        coalesce(cmpRemainingCondensate::VARCHAR, ''),
        coalesce(cmpRemainingOE::VARCHAR, ''),
        coalesce(cmpDateOffResEstDisplay::VARCHAR, ''),
        coalesce(cmpShare::VARCHAR, '')
    ))                                              AS ___Std_md5,
    filename                                        AS ___Std_filename,
    year_month::VARCHAR                             AS ___Std_year_month,
    strptime(regexp_extract(filename, '_(\d{8}_\d{4})\.[^./]+$', 1) || ' +0000',
             '%Y%m%d_%H%M %z')                      AS ___Std_file_timestamp
FROM read_parquet(
    's3://hydroc-std/no_sodir/company_reserves/*/*.parquet',
    hive_partitioning = true,
    filename = true,
    union_by_name = true
);
