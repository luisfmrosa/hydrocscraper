-- Std: Sodir company reserves (tabular, no flattening, one row per field and licensee company).
-- Converts one Raw file, given by the runner as the variable raw_file (full
-- s3:// path), to one typed Parquet file in Std with the Raw file's
-- year_month and timestamp:
--   s3://hydroc-std/no_sodir/company_reserves/year_month=<ym>/no_sodir_company_reserves_<ts>.parquet
-- Key first, then the other columns in the file's order. Rerunning overwrites
-- the same file.
--
-- Checks (each fails the step; the watermark stays at 'raw' and the next run
-- retries once the script is fixed):
--   - schema: the file's columns must be exactly the expected ones. The raw
--     view reads every file with union_by_name, so without this a renamed or
--     dropped column would silently become NULL;
--   - types: a value that doesn't cast, or a date not in dd.mm.yyyy;
--   - the five remaining volumes and cmpShare (percent, 5 decimals)
--     become DOUBLE. The shares of a field need not sum to 100 (not
--     checked).
-- Empty values are NULL (the CSV reader's default).
WITH actual AS (
    SELECT column_name
    FROM (DESCRIBE FROM read_csv(getvariable('raw_file'), all_varchar = true, hive_partitioning = false))
),
expected(column_name) AS (VALUES
    ('cmpLongName'), ('fldName'), ('cmpRemainingOil'), ('cmpRemainingGas'), ('cmpRemainingNGL'),
    ('cmpRemainingCondensate'), ('cmpRemainingOE'), ('cmpDateOffResEstDisplay'), ('cmpShare'),
    ('fldNpdidField'), ('cmpNpdidCompany'), ('DatesyncNPD')
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
    's3://hydroc-std/no_sodir/company_reserves/year_month='
    || regexp_extract(getvariable('raw_file'), 'year_month=([^/]+)/', 1)
    || '/no_sodir_company_reserves_'
    || regexp_extract(getvariable('raw_file'), '_(\d{8}_\d{4})\.[^./]+$', 1)
    || '.parquet';

COPY (
    SELECT
        fldNpdidField::BIGINT                           AS fldNpdidField,
        cmpNpdidCompany::BIGINT                         AS cmpNpdidCompany,
        cmpLongName::VARCHAR                            AS cmpLongName,
        fldName::VARCHAR                                AS fldName,
        cmpRemainingOil::DOUBLE                         AS cmpRemainingOil,
        cmpRemainingGas::DOUBLE                         AS cmpRemainingGas,
        cmpRemainingNGL::DOUBLE                         AS cmpRemainingNGL,
        cmpRemainingCondensate::DOUBLE                  AS cmpRemainingCondensate,
        cmpRemainingOE::DOUBLE                          AS cmpRemainingOE,
        strptime(cmpDateOffResEstDisplay, '%d.%m.%Y')::DATE AS cmpDateOffResEstDisplay,
        cmpShare::DOUBLE                                AS cmpShare,
        strptime(DatesyncNPD, '%d.%m.%Y')::DATE         AS DatesyncNPD
    FROM hook.raw_views.no_sodir_company_reserves
    WHERE ___Raw_filename = getvariable('raw_file')
) TO (getvariable('std_file')) (FORMAT parquet);
