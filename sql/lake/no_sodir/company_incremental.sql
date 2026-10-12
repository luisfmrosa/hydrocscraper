-- Incremental Lake load: Sodir companies.
-- Compares the Std file of the latest watermark with the Lake's current state
-- (latest row per key) and appends:
--   - new rows: unknown key, or key whose latest row is a deletion
--   - changed rows: different MD5 of the non-key columns
--   - deletion rows: current keys missing from the file (last known values)
-- Re-running it adds nothing; a file older than the Lake's latest load is
-- ignored. Run by the app after the Std step of the incremental download.
INSERT INTO lake.no_sodir.company (
    cmpNpdidCompany, cmpLongName, cmpOrgNumberBrReg, cmpShortName, cmpNationCode, cmpSurveyPrefix,
    cmpLicenceOperCurrent, cmpLicenceOperFormer, cmpLicenceLicenseeCurrent,
    cmpLicenceLicenseeFormer, cmpTufOperCurrent, cmpTufOperFormer, cmpTufPartnerCurrent,
    cmpTufPartnerFormer, cmpBsnsArrAreaOperCurrent, cmpBsnsArrAreaOperFormer,
    cmpBsnsArrAreaPartnerCurrent, cmpBsnsArrAreaPartnerFormer, dateSyncNPD,
    ___Lake_md5, ___Lake_load_timestamp, ___Lake_datasource, ___Lake_sourcefile, ___Lake_isdeleted
)
WITH incoming AS (
    -- rows of the latest watermark's file, unless the Lake is already newer
    SELECT r.*
    FROM hook.std_views.no_sodir_company r
    JOIN hook.metadata.watermark_latest w
      ON w.source = 'no_sodir'
     AND w.dataset = 'company'
     -- the Std file derived from the watermark's Raw file (same year_month and timestamp)
     AND r.___Std_filename = 's3://hydroc-std/no_sodir/company/year_month='
         || regexp_extract(w.raw_file, 'year_month=([^/]+)/', 1)
         || '/no_sodir_company_'
         || regexp_extract(w.raw_file, '_(\d{8}_\d{4})\.[^./]+$', 1)
         || '.parquet'
    WHERE r.___Std_file_timestamp >= (
        SELECT coalesce(max(___Lake_load_timestamp), '-infinity'::TIMESTAMPTZ)
        FROM lake.no_sodir.company
    )
),
batch AS (
    SELECT DISTINCT ___Std_filename, ___Std_file_timestamp FROM incoming
),
current_state AS (
    SELECT *
    FROM lake.no_sodir.company
    QUALIFY row_number() OVER (
        PARTITION BY cmpNpdidCompany
        ORDER BY ___Lake_load_timestamp DESC
    ) = 1
)
-- new and changed rows
SELECT
    i.cmpNpdidCompany, i.cmpLongName, i.cmpOrgNumberBrReg, i.cmpShortName, i.cmpNationCode,
    i.cmpSurveyPrefix, i.cmpLicenceOperCurrent, i.cmpLicenceOperFormer,
    i.cmpLicenceLicenseeCurrent, i.cmpLicenceLicenseeFormer, i.cmpTufOperCurrent,
    i.cmpTufOperFormer, i.cmpTufPartnerCurrent, i.cmpTufPartnerFormer, i.cmpBsnsArrAreaOperCurrent,
    i.cmpBsnsArrAreaOperFormer, i.cmpBsnsArrAreaPartnerCurrent, i.cmpBsnsArrAreaPartnerFormer,
    i.dateSyncNPD,
    i.___Std_md5, i.___Std_file_timestamp, 'no_sodir_company', i.___Std_filename, false
FROM incoming i
LEFT JOIN current_state c
  ON  c.cmpNpdidCompany = i.cmpNpdidCompany
WHERE c.___Lake_md5 IS NULL            -- new key
   OR c.___Lake_isdeleted              -- key comes back
   OR c.___Lake_md5 <> i.___Std_md5    -- changed values
UNION ALL
-- deleted rows: current keys absent from the file
SELECT
    c.cmpNpdidCompany, c.cmpLongName, c.cmpOrgNumberBrReg, c.cmpShortName, c.cmpNationCode,
    c.cmpSurveyPrefix, c.cmpLicenceOperCurrent, c.cmpLicenceOperFormer,
    c.cmpLicenceLicenseeCurrent, c.cmpLicenceLicenseeFormer, c.cmpTufOperCurrent,
    c.cmpTufOperFormer, c.cmpTufPartnerCurrent, c.cmpTufPartnerFormer, c.cmpBsnsArrAreaOperCurrent,
    c.cmpBsnsArrAreaOperFormer, c.cmpBsnsArrAreaPartnerCurrent, c.cmpBsnsArrAreaPartnerFormer,
    c.dateSyncNPD,
    c.___Lake_md5, b.___Std_file_timestamp, 'no_sodir_company', b.___Std_filename, true
FROM current_state c
CROSS JOIN batch b
WHERE NOT c.___Lake_isdeleted
  AND NOT EXISTS (
      SELECT 1 FROM incoming i
      WHERE i.cmpNpdidCompany = c.cmpNpdidCompany
  );
