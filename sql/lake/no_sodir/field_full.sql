-- Full Lake load: Sodir fields.
-- Empties the Lake table, then replays every file in Std from oldest to
-- newest in one set-based statement. The result is the same as running the
-- incremental load once per file, in order:
--   - new rows: first appearance of a key, or reappearance after a gap
--   - changed rows: MD5 differs from the key's previous file
--   - deletion rows: in the file right after a key's last appearance
--     (repeating its last known values)
-- Run by the app after the full download and the Std rebuild.
TRUNCATE lake.no_sodir.field;

INSERT INTO lake.no_sodir.field (
    fldNpdidField, fldName, cmpLongName, fldCurrentActivitySatus, wlbName, wlbCompletionDate,
    fldMainArea, fldOwnerKind, fldOwnerName, fldMainSupplyBase, fldHcType, fldNpdidOwner,
    wlbNpdidWellbore, cmpNpdidCompany, fldFactPageUrl, fldFactMapUrl, fldDateUpdated,
    fldDateUpdatedMax, DatesyncNPD,
    ___Lake_md5, ___Lake_load_timestamp, ___Lake_datasource, ___Lake_sourcefile, ___Lake_isdeleted
)
WITH files AS (
    -- every Std file, numbered by download time
    SELECT ___Std_filename, ___Std_file_timestamp,
           row_number() OVER (ORDER BY ___Std_file_timestamp, ___Std_filename) AS file_seq
    FROM (
        SELECT DISTINCT ___Std_filename, ___Std_file_timestamp
        FROM hook.std_views.no_sodir_field
    )
),
observations AS (
    -- each key in each file, with its previous and next appearance
    SELECT r.*, f.file_seq,
           lag(r.___Std_md5) OVER k AS prev_md5,
           lag(f.file_seq)   OVER k AS prev_seq,
           lead(f.file_seq)  OVER k AS next_seq
    FROM hook.std_views.no_sodir_field r
    JOIN files f USING (___Std_filename, ___Std_file_timestamp)
    WINDOW k AS (
        PARTITION BY r.fldNpdidField
        ORDER BY f.file_seq
    )
)
-- new, reappearing and changed rows
SELECT
    o.fldNpdidField, o.fldName, o.cmpLongName, o.fldCurrentActivitySatus, o.wlbName, o.wlbCompletionDate,
    o.fldMainArea, o.fldOwnerKind, o.fldOwnerName, o.fldMainSupplyBase, o.fldHcType, o.fldNpdidOwner,
    o.wlbNpdidWellbore, o.cmpNpdidCompany, o.fldFactPageUrl, o.fldFactMapUrl, o.fldDateUpdated,
    o.fldDateUpdatedMax, o.DatesyncNPD,
    o.___Std_md5, o.___Std_file_timestamp, 'no_sodir_field', o.___Std_filename, false
FROM observations o
WHERE o.prev_seq IS NULL                   -- first appearance
   OR o.prev_seq < o.file_seq - 1          -- reappears after being deleted
   OR o.prev_md5 <> o.___Std_md5           -- changed values
UNION ALL
-- deletion rows: the key is missing from the next file
SELECT
    o.fldNpdidField, o.fldName, o.cmpLongName, o.fldCurrentActivitySatus, o.wlbName, o.wlbCompletionDate,
    o.fldMainArea, o.fldOwnerKind, o.fldOwnerName, o.fldMainSupplyBase, o.fldHcType, o.fldNpdidOwner,
    o.wlbNpdidWellbore, o.cmpNpdidCompany, o.fldFactPageUrl, o.fldFactMapUrl, o.fldDateUpdated,
    o.fldDateUpdatedMax, o.DatesyncNPD,
    o.___Std_md5, nf.___Std_file_timestamp, 'no_sodir_field', nf.___Std_filename, true
FROM observations o
JOIN files nf ON nf.file_seq = o.file_seq + 1
WHERE o.next_seq IS NULL OR o.next_seq > o.file_seq + 1;
