-- Incremental Lake load: NPD monthly field production.
-- Compares the Std file of the latest watermark with the Lake's current state
-- (latest row per key) and appends:
--   - new rows: unknown key, or key whose latest row is a deletion
--   - changed rows: different MD5 of the non-key columns
--   - deletion rows: current keys missing from the file (last known values)
-- Re-running it adds nothing; a file older than the Lake's latest load is
-- ignored. Run by the app after the Std step of the incremental download.
INSERT INTO lake.npd.field_production_monthly (
    prfNpdidInformationCarrier, prfYear, prfMonth, prfInformationCarrier,
    prfPrdOilNetMillSm3, prfPrdGasNetBillSm3, prfPrdNGLNetMillSm3,
    prfPrdCondensateNetMillSm3, prfPrdOeNetMillSm3, prfPrdProducedWaterInFieldMillSm3,
    ___Lake_md5, ___Lake_load_timestamp, ___Lake_datasource, ___Lake_sourcefile, ___Lake_isdeleted
)
WITH incoming AS (
    -- rows of the latest watermark's file, unless the Lake is already newer
    SELECT r.*
    FROM hook.std_views.npd_field_production_monthly r
    JOIN hook.metadata.watermark_latest w
      ON w.source = 'npd'
     AND w.dataset = 'field_production_monthly'
     -- the Std file derived from the watermark's Raw file (same year_month and timestamp)
     AND r.___Std_filename = 's3://hydroc-std/npd/field_production_monthly/year_month='
         || regexp_extract(w.raw_file, 'year_month=([^/]+)/', 1)
         || '/npd_field_production_monthly_'
         || regexp_extract(w.raw_file, '_(\d{8}_\d{4})\.[^./]+$', 1)
         || '.parquet'
    WHERE r.___Std_file_timestamp >= (
        SELECT coalesce(max(___Lake_load_timestamp), '-infinity'::TIMESTAMPTZ)
        FROM lake.npd.field_production_monthly
    )
),
batch AS (
    SELECT DISTINCT ___Std_filename, ___Std_file_timestamp FROM incoming
),
current_state AS (
    SELECT *
    FROM lake.npd.field_production_monthly
    QUALIFY row_number() OVER (
        PARTITION BY prfNpdidInformationCarrier, prfYear, prfMonth
        ORDER BY ___Lake_load_timestamp DESC
    ) = 1
)
-- new and changed rows
SELECT
    i.prfNpdidInformationCarrier, i.prfYear, i.prfMonth, i.prfInformationCarrier,
    i.prfPrdOilNetMillSm3, i.prfPrdGasNetBillSm3, i.prfPrdNGLNetMillSm3,
    i.prfPrdCondensateNetMillSm3, i.prfPrdOeNetMillSm3, i.prfPrdProducedWaterInFieldMillSm3,
    i.___Std_md5, i.___Std_file_timestamp, 'npd_field_production_monthly', i.___Std_filename, false
FROM incoming i
LEFT JOIN current_state c
  ON  c.prfNpdidInformationCarrier = i.prfNpdidInformationCarrier
  AND c.prfYear = i.prfYear
  AND c.prfMonth = i.prfMonth
WHERE c.___Lake_md5 IS NULL            -- new key
   OR c.___Lake_isdeleted              -- key comes back
   OR c.___Lake_md5 <> i.___Std_md5    -- changed values
UNION ALL
-- deleted rows: current keys absent from the file
SELECT
    c.prfNpdidInformationCarrier, c.prfYear, c.prfMonth, c.prfInformationCarrier,
    c.prfPrdOilNetMillSm3, c.prfPrdGasNetBillSm3, c.prfPrdNGLNetMillSm3,
    c.prfPrdCondensateNetMillSm3, c.prfPrdOeNetMillSm3, c.prfPrdProducedWaterInFieldMillSm3,
    c.___Lake_md5, b.___Std_file_timestamp, 'npd_field_production_monthly', b.___Std_filename, true
FROM current_state c
CROSS JOIN batch b
WHERE NOT c.___Lake_isdeleted
  AND NOT EXISTS (
      SELECT 1 FROM incoming i
      WHERE i.prfNpdidInformationCarrier = c.prfNpdidInformationCarrier
        AND i.prfYear = c.prfYear
        AND i.prfMonth = c.prfMonth
  );
