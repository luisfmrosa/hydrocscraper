-- Std view: Sodir fields, every Std file.
-- Business key: fldNpdidField
-- Loaded into the Lake by sql/lake/no_sodir/field_{full,incremental}.sql.
--
-- Data columns: as written by sql/std/no_sodir/field.sql (already typed),
-- same names and order as the Lake table. Then the Std metadata columns:
--   ___Std_md5             MD5 of the non-key columns, in this order, joined
--                          with chr(31); NULL becomes ''. Leaves out
--                          fldDateUpdatedMax and DatesyncNPD: Sodir moves
--                          them with every export, so they would make a new
--                          version of every field each day
--   ___Std_filename        full S3 path of the Std file
--   ___Std_year_month      year_month partition (the Raw file's)
--   ___Std_file_timestamp  download time (UTC) of the Raw file, from the
--                          file name suffix
--
-- CREATE OR REPLACE: the definition must follow the repository. Fails while
-- the dataset has no Std files yet; the app re-runs this script before every
-- Lake load.
CREATE OR REPLACE VIEW hook.std_views.no_sodir_field AS
SELECT
    fldNpdidField,
    fldName,
    cmpLongName,
    fldCurrentActivitySatus,
    wlbName,
    wlbCompletionDate,
    fldMainArea,
    fldOwnerKind,
    fldOwnerName,
    fldMainSupplyBase,
    fldHcType,
    fldNpdidOwner,
    wlbNpdidWellbore,
    cmpNpdidCompany,
    fldFactPageUrl,
    fldFactMapUrl,
    fldDateUpdated,
    fldDateUpdatedMax,
    DatesyncNPD,
    md5(concat_ws(chr(31),
        coalesce(fldName::VARCHAR, ''),
        coalesce(cmpLongName::VARCHAR, ''),
        coalesce(fldCurrentActivitySatus::VARCHAR, ''),
        coalesce(wlbName::VARCHAR, ''),
        coalesce(wlbCompletionDate::VARCHAR, ''),
        coalesce(fldMainArea::VARCHAR, ''),
        coalesce(fldOwnerKind::VARCHAR, ''),
        coalesce(fldOwnerName::VARCHAR, ''),
        coalesce(fldMainSupplyBase::VARCHAR, ''),
        coalesce(fldHcType::VARCHAR, ''),
        coalesce(fldNpdidOwner::VARCHAR, ''),
        coalesce(wlbNpdidWellbore::VARCHAR, ''),
        coalesce(cmpNpdidCompany::VARCHAR, ''),
        coalesce(fldFactPageUrl::VARCHAR, ''),
        coalesce(fldFactMapUrl::VARCHAR, ''),
        coalesce(fldDateUpdated::VARCHAR, '')
    ))                                              AS ___Std_md5,
    filename                                        AS ___Std_filename,
    year_month::VARCHAR                             AS ___Std_year_month,
    strptime(regexp_extract(filename, '_(\d{8}_\d{4})\.[^./]+$', 1) || ' +0000',
             '%Y%m%d_%H%M %z')                      AS ___Std_file_timestamp
FROM read_parquet(
    's3://hydroc-std/no_sodir/field/*/*.parquet',
    hive_partitioning = true,
    filename = true,
    union_by_name = true
);
