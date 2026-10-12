-- Std: Sodir companies (tabular, no flattening, one row per company).
-- Converts one Raw file, given by the runner as the variable raw_file (full
-- s3:// path), to one typed Parquet file in Std with the Raw file's
-- year_month and timestamp:
--   s3://hydroc-std/no_sodir/company/year_month=<ym>/no_sodir_company_<ts>.parquet
-- Key first, then the other columns in the file's order. Rerunning overwrites
-- the same file.
--
-- Checks (each fails the step; the watermark stays at 'raw' and the next run
-- retries once the script is fixed):
--   - schema: the file's columns must be exactly the expected ones. The raw
--     view reads every file with union_by_name, so without this a renamed or
--     dropped column would silently become NULL;
--   - types: a value that doesn't cast, or a date not in dd.mm.yyyy;
--   - flags: the twelve Y/N columns must hold Y or N (an empty value
--     fails too); they become BOOLEAN;
--   - cmpOrgNumberBrReg: kept as text (foreign numbers such as SC 362013);
--     a blank-only value becomes NULL.
-- Empty values are NULL (the CSV reader's default).
WITH actual AS (
    SELECT column_name
    FROM (DESCRIBE FROM read_csv(getvariable('raw_file'), all_varchar = true, hive_partitioning = false))
),
expected(column_name) AS (VALUES
    ('cmpLongName'), ('cmpOrgNumberBrReg'), ('cmpShortName'), ('cmpNationCode'),
    ('cmpSurveyPrefix'), ('cmpNpdidCompany'), ('cmpLicenceOperCurrent'), ('cmpLicenceOperFormer'),
    ('cmpLicenceLicenseeCurrent'), ('cmpLicenceLicenseeFormer'), ('cmpTufOperCurrent'),
    ('cmpTufOperFormer'), ('cmpTufPartnerCurrent'), ('cmpTufPartnerFormer'),
    ('cmpBsnsArrAreaOperCurrent'), ('cmpBsnsArrAreaOperFormer'), ('cmpBsnsArrAreaPartnerCurrent'),
    ('cmpBsnsArrAreaPartnerFormer'), ('dateSyncNPD')
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

-- Flags: every Y/N column holds Y or N
SELECT error('Unexpected flag values in ' || getvariable('raw_file') || ': '
             || string_agg(DISTINCT msg, ', ' ORDER BY msg))
FROM (
    SELECT unnest([
            CASE WHEN coalesce(cmpLicenceOperCurrent, '') NOT IN ('Y', 'N') THEN 'cmpLicenceOperCurrent=' || coalesce(cmpLicenceOperCurrent, 'NULL') END,
            CASE WHEN coalesce(cmpLicenceOperFormer, '') NOT IN ('Y', 'N') THEN 'cmpLicenceOperFormer=' || coalesce(cmpLicenceOperFormer, 'NULL') END,
            CASE WHEN coalesce(cmpLicenceLicenseeCurrent, '') NOT IN ('Y', 'N') THEN 'cmpLicenceLicenseeCurrent=' || coalesce(cmpLicenceLicenseeCurrent, 'NULL') END,
            CASE WHEN coalesce(cmpLicenceLicenseeFormer, '') NOT IN ('Y', 'N') THEN 'cmpLicenceLicenseeFormer=' || coalesce(cmpLicenceLicenseeFormer, 'NULL') END,
            CASE WHEN coalesce(cmpTufOperCurrent, '') NOT IN ('Y', 'N') THEN 'cmpTufOperCurrent=' || coalesce(cmpTufOperCurrent, 'NULL') END,
            CASE WHEN coalesce(cmpTufOperFormer, '') NOT IN ('Y', 'N') THEN 'cmpTufOperFormer=' || coalesce(cmpTufOperFormer, 'NULL') END,
            CASE WHEN coalesce(cmpTufPartnerCurrent, '') NOT IN ('Y', 'N') THEN 'cmpTufPartnerCurrent=' || coalesce(cmpTufPartnerCurrent, 'NULL') END,
            CASE WHEN coalesce(cmpTufPartnerFormer, '') NOT IN ('Y', 'N') THEN 'cmpTufPartnerFormer=' || coalesce(cmpTufPartnerFormer, 'NULL') END,
            CASE WHEN coalesce(cmpBsnsArrAreaOperCurrent, '') NOT IN ('Y', 'N') THEN 'cmpBsnsArrAreaOperCurrent=' || coalesce(cmpBsnsArrAreaOperCurrent, 'NULL') END,
            CASE WHEN coalesce(cmpBsnsArrAreaOperFormer, '') NOT IN ('Y', 'N') THEN 'cmpBsnsArrAreaOperFormer=' || coalesce(cmpBsnsArrAreaOperFormer, 'NULL') END,
            CASE WHEN coalesce(cmpBsnsArrAreaPartnerCurrent, '') NOT IN ('Y', 'N') THEN 'cmpBsnsArrAreaPartnerCurrent=' || coalesce(cmpBsnsArrAreaPartnerCurrent, 'NULL') END,
            CASE WHEN coalesce(cmpBsnsArrAreaPartnerFormer, '') NOT IN ('Y', 'N') THEN 'cmpBsnsArrAreaPartnerFormer=' || coalesce(cmpBsnsArrAreaPartnerFormer, 'NULL') END
    ]) AS msg
    FROM hook.raw_views.no_sodir_company
    WHERE ___Raw_filename = getvariable('raw_file')
)
WHERE msg IS NOT NULL
HAVING count(*) > 0;

SET VARIABLE std_file =
    's3://hydroc-std/no_sodir/company/year_month='
    || regexp_extract(getvariable('raw_file'), 'year_month=([^/]+)/', 1)
    || '/no_sodir_company_'
    || regexp_extract(getvariable('raw_file'), '_(\d{8}_\d{4})\.[^./]+$', 1)
    || '.parquet';

COPY (
    SELECT
        cmpNpdidCompany::BIGINT                         AS cmpNpdidCompany,
        cmpLongName::VARCHAR                            AS cmpLongName,
        nullif(trim(cmpOrgNumberBrReg), '')             AS cmpOrgNumberBrReg,
        cmpShortName::VARCHAR                           AS cmpShortName,
        cmpNationCode::VARCHAR                          AS cmpNationCode,
        cmpSurveyPrefix::VARCHAR                        AS cmpSurveyPrefix,
        (cmpLicenceOperCurrent = 'Y')                   AS cmpLicenceOperCurrent,
        (cmpLicenceOperFormer = 'Y')                    AS cmpLicenceOperFormer,
        (cmpLicenceLicenseeCurrent = 'Y')               AS cmpLicenceLicenseeCurrent,
        (cmpLicenceLicenseeFormer = 'Y')                AS cmpLicenceLicenseeFormer,
        (cmpTufOperCurrent = 'Y')                       AS cmpTufOperCurrent,
        (cmpTufOperFormer = 'Y')                        AS cmpTufOperFormer,
        (cmpTufPartnerCurrent = 'Y')                    AS cmpTufPartnerCurrent,
        (cmpTufPartnerFormer = 'Y')                     AS cmpTufPartnerFormer,
        (cmpBsnsArrAreaOperCurrent = 'Y')               AS cmpBsnsArrAreaOperCurrent,
        (cmpBsnsArrAreaOperFormer = 'Y')                AS cmpBsnsArrAreaOperFormer,
        (cmpBsnsArrAreaPartnerCurrent = 'Y')            AS cmpBsnsArrAreaPartnerCurrent,
        (cmpBsnsArrAreaPartnerFormer = 'Y')             AS cmpBsnsArrAreaPartnerFormer,
        strptime(dateSyncNPD, '%d.%m.%Y')::DATE         AS dateSyncNPD
    FROM hook.raw_views.no_sodir_company
    WHERE ___Raw_filename = getvariable('raw_file')
) TO (getvariable('std_file')) (FORMAT parquet);
