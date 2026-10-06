-- Incremental Lake load: Sodir fields.
-- Compares the Std file of the latest watermark with the Lake's current state
-- (latest row per key) and appends:
--   - new rows: unknown key, or key whose latest row is a deletion
--   - changed rows: different MD5 of the non-key columns
--   - deletion rows: current keys missing from the file (last known values)
-- Re-running it adds nothing; a file older than the Lake's latest load is
-- ignored. Run by the app after the Std step of the incremental download.
INSERT INTO lake.no_sodir.field (
    fldNpdidField, fldName, cmpLongName, fldCurrentActivitySatus, wlbName, wlbCompletionDate,
    fldMainArea, fldOwnerKind, fldOwnerName, fldMainSupplyBase, fldHcType, fldNpdidOwner,
    wlbNpdidWellbore, cmpNpdidCompany, fldFactPageUrl, fldFactMapUrl, fldDateUpdated,
    fldDateUpdatedMax, DatesyncNPD,
    ___Lake_md5, ___Lake_load_timestamp, ___Lake_datasource, ___Lake_sourcefile, ___Lake_isdeleted
)
WITH incoming AS (
    -- rows of the latest watermark's file, unless the Lake is already newer
    SELECT r.*
    FROM hook.std_views.no_sodir_field r
    JOIN hook.metadata.watermark_latest w
      ON w.source = 'no_sodir'
     AND w.dataset = 'field'
     -- the Std file derived from the watermark's Raw file (same year_month and timestamp)
     AND r.___Std_filename = 's3://hydroc-std/no_sodir/field/year_month='
         || regexp_extract(w.raw_file, 'year_month=([^/]+)/', 1)
         || '/no_sodir_field_'
         || regexp_extract(w.raw_file, '_(\d{8}_\d{4})\.[^./]+$', 1)
         || '.parquet'
    WHERE r.___Std_file_timestamp >= (
        SELECT coalesce(max(___Lake_load_timestamp), '-infinity'::TIMESTAMPTZ)
        FROM lake.no_sodir.field
    )
),
batch AS (
    SELECT DISTINCT ___Std_filename, ___Std_file_timestamp FROM incoming
),
current_state AS (
    SELECT *
    FROM lake.no_sodir.field
    QUALIFY row_number() OVER (
        PARTITION BY fldNpdidField
        ORDER BY ___Lake_load_timestamp DESC
    ) = 1
)
-- new and changed rows
SELECT
    i.fldNpdidField, i.fldName, i.cmpLongName, i.fldCurrentActivitySatus, i.wlbName, i.wlbCompletionDate,
    i.fldMainArea, i.fldOwnerKind, i.fldOwnerName, i.fldMainSupplyBase, i.fldHcType, i.fldNpdidOwner,
    i.wlbNpdidWellbore, i.cmpNpdidCompany, i.fldFactPageUrl, i.fldFactMapUrl, i.fldDateUpdated,
    i.fldDateUpdatedMax, i.DatesyncNPD,
    i.___Std_md5, i.___Std_file_timestamp, 'no_sodir_field', i.___Std_filename, false
FROM incoming i
LEFT JOIN current_state c
  ON  c.fldNpdidField = i.fldNpdidField
WHERE c.___Lake_md5 IS NULL            -- new key
   OR c.___Lake_isdeleted              -- key comes back
   OR c.___Lake_md5 <> i.___Std_md5    -- changed values
UNION ALL
-- deleted rows: current keys absent from the file
SELECT
    c.fldNpdidField, c.fldName, c.cmpLongName, c.fldCurrentActivitySatus, c.wlbName, c.wlbCompletionDate,
    c.fldMainArea, c.fldOwnerKind, c.fldOwnerName, c.fldMainSupplyBase, c.fldHcType, c.fldNpdidOwner,
    c.wlbNpdidWellbore, c.cmpNpdidCompany, c.fldFactPageUrl, c.fldFactMapUrl, c.fldDateUpdated,
    c.fldDateUpdatedMax, c.DatesyncNPD,
    c.___Lake_md5, b.___Std_file_timestamp, 'no_sodir_field', b.___Std_filename, true
FROM current_state c
CROSS JOIN batch b
WHERE NOT c.___Lake_isdeleted
  AND NOT EXISTS (
      SELECT 1 FROM incoming i
      WHERE i.fldNpdidField = c.fldNpdidField
  );
