-- Std: Sodir fields (tabular, no flattening, one row per field).
-- Converts one Raw file, given by the runner as the variable raw_file (full
-- s3:// path), to one typed Parquet file in Std with the Raw file's
-- year_month and timestamp:
--   s3://hydroc-std/no_sodir/field/year_month=<ym>/no_sodir_field_<ts>.parquet
-- Key first, then the other columns in the file's order. Rerunning overwrites
-- the same file.
--
-- Checks (each fails the step; the watermark stays at 'raw' and the next run
-- retries once the script is fixed):
--   - schema: the file's columns must be exactly the expected ones. The raw
--     view reads every file with union_by_name, so without this a renamed or
--     dropped column would silently become NULL;
--   - types: a value that doesn't cast, or a date not in dd.mm.yyyy.
-- Empty values are NULL (the CSV reader's default).
WITH actual AS (
    SELECT column_name
    FROM (DESCRIBE FROM read_csv(getvariable('raw_file'), all_varchar = true, hive_partitioning = false))
),
expected(column_name) AS (VALUES
    ('fldName'), ('cmpLongName'), ('fldCurrentActivitySatus'), ('wlbName'), ('wlbCompletionDate'),
    ('fldMainArea'), ('fldOwnerKind'), ('fldOwnerName'), ('fldMainSupplyBase'), ('fldHcType'),
    ('fldNpdidOwner'), ('fldNpdidField'), ('wlbNpdidWellbore'), ('cmpNpdidCompany'),
    ('fldFactPageUrl'), ('fldFactMapUrl'), ('fldDateUpdated'), ('fldDateUpdatedMax'), ('DatesyncNPD')
),
diff AS (
    SELECT 'missing: ' || string_agg(column_name, ', ' ORDER BY column_name) AS msg
    FROM (FROM expected EXCEPT FROM actual) HAVING count(*) > 0
    UNION ALL
    SELECT 'unexpected: ' || string_agg(column_name, ', ' ORDER BY column_name)
    FROM (FROM actual EXCEPT FROM expected) HAVING count(*) > 0
)
SELECT error('Schema of ' || getvariable('raw_file') || ' changed: ' || string_agg(msg, '; '))
FROM diff
HAVING count(*) > 0;

SET VARIABLE std_file =
    's3://hydroc-std/no_sodir/field/year_month='
    || regexp_extract(getvariable('raw_file'), 'year_month=([^/]+)/', 1)
    || '/no_sodir_field_'
    || regexp_extract(getvariable('raw_file'), '_(\d{8}_\d{4})\.[^./]+$', 1)
    || '.parquet';

COPY (
    SELECT
        fldNpdidField::BIGINT                           AS fldNpdidField,
        fldName::VARCHAR                                AS fldName,
        cmpLongName::VARCHAR                            AS cmpLongName,
        fldCurrentActivitySatus::VARCHAR                AS fldCurrentActivitySatus,
        wlbName::VARCHAR                                AS wlbName,
        strptime(wlbCompletionDate, '%d.%m.%Y')::DATE   AS wlbCompletionDate,
        fldMainArea::VARCHAR                            AS fldMainArea,
        fldOwnerKind::VARCHAR                           AS fldOwnerKind,
        fldOwnerName::VARCHAR                           AS fldOwnerName,
        fldMainSupplyBase::VARCHAR                      AS fldMainSupplyBase,
        fldHcType::VARCHAR                              AS fldHcType,
        fldNpdidOwner::BIGINT                           AS fldNpdidOwner,
        wlbNpdidWellbore::BIGINT                        AS wlbNpdidWellbore,
        cmpNpdidCompany::BIGINT                         AS cmpNpdidCompany,
        fldFactPageUrl::VARCHAR                         AS fldFactPageUrl,
        fldFactMapUrl::VARCHAR                          AS fldFactMapUrl,
        strptime(fldDateUpdated, '%d.%m.%Y')::DATE      AS fldDateUpdated,
        strptime(fldDateUpdatedMax, '%d.%m.%Y')::DATE   AS fldDateUpdatedMax,
        strptime(DatesyncNPD, '%d.%m.%Y')::DATE         AS DatesyncNPD
    FROM hook.raw_views.no_sodir_field
    WHERE ___Raw_filename = getvariable('raw_file')
) TO (getvariable('std_file')) (FORMAT parquet);
