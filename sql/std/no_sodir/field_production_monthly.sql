-- Std: Sodir monthly field production (tabular, no flattening).
-- Converts one Raw file, given by the runner as the variable raw_file (full
-- s3:// path), to one typed Parquet file in Std with the Raw file's
-- year_month and timestamp:
--   s3://hydroc-std/no_sodir/field_production_monthly/year_month=<ym>/no_sodir_field_production_monthly_<ts>.parquet
-- Keys first, then the other columns. Rerunning overwrites the same file.
--
-- Checks (each fails the step; the watermark stays at 'raw' and the next run
-- retries once the script is fixed):
--   - schema: the file's columns must be exactly the expected ones. The raw
--     view reads every file with union_by_name, so without this a renamed or
--     dropped column would silently become NULL;
--   - types: a value that doesn't cast.
WITH actual AS (
    SELECT column_name
    FROM (DESCRIBE FROM read_csv(getvariable('raw_file'), all_varchar = true, hive_partitioning = false))
),
expected(column_name) AS (VALUES
    ('prfInformationCarrier'), ('prfYear'), ('prfMonth'), ('prfPrdOilNetMillSm3'),
    ('prfPrdGasNetBillSm3'), ('prfPrdNGLNetMillSm3'), ('prfPrdCondensateNetMillSm3'),
    ('prfPrdOeNetMillSm3'), ('prfPrdProducedWaterInFieldMillSm3'), ('prfNpdidInformationCarrier')
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
    's3://hydroc-std/no_sodir/field_production_monthly/year_month='
    || regexp_extract(getvariable('raw_file'), 'year_month=([^/]+)/', 1)
    || '/no_sodir_field_production_monthly_'
    || regexp_extract(getvariable('raw_file'), '_(\d{8}_\d{4})\.[^./]+$', 1)
    || '.parquet';

COPY (
    SELECT
        prfNpdidInformationCarrier::BIGINT              AS prfNpdidInformationCarrier,
        prfYear::INTEGER                                AS prfYear,
        prfMonth::INTEGER                               AS prfMonth,
        prfInformationCarrier::VARCHAR                  AS prfInformationCarrier,
        prfPrdOilNetMillSm3::DOUBLE                     AS prfPrdOilNetMillSm3,
        prfPrdGasNetBillSm3::DOUBLE                     AS prfPrdGasNetBillSm3,
        prfPrdNGLNetMillSm3::DOUBLE                     AS prfPrdNGLNetMillSm3,
        prfPrdCondensateNetMillSm3::DOUBLE              AS prfPrdCondensateNetMillSm3,
        prfPrdOeNetMillSm3::DOUBLE                      AS prfPrdOeNetMillSm3,
        prfPrdProducedWaterInFieldMillSm3::DOUBLE       AS prfPrdProducedWaterInFieldMillSm3
    FROM hook.raw_views.no_sodir_field_production_monthly
    WHERE ___Raw_filename = getvariable('raw_file')
) TO (getvariable('std_file')) (FORMAT parquet);
