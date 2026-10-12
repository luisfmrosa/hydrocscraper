-- Full Lake load: Sodir company reserves.
-- Empties the Lake table, then replays every file in Std from oldest to
-- newest in one set-based statement. The result is the same as running the
-- incremental load once per file, in order:
--   - new rows: first appearance of a key, or reappearance after a gap
--   - changed rows: MD5 differs from the key's previous file
--   - deletion rows: in the file right after a key's last appearance
--     (repeating its last known values)
-- Run by the app after the full download and the Std rebuild.
TRUNCATE lake.no_sodir.company_reserves;

INSERT INTO lake.no_sodir.company_reserves (
    fldNpdidField, cmpNpdidCompany, cmpLongName, fldName, cmpRemainingOil, cmpRemainingGas,
    cmpRemainingNGL, cmpRemainingCondensate, cmpRemainingOE, cmpDateOffResEstDisplay, cmpShare,
    DatesyncNPD,
    ___Lake_md5, ___Lake_load_timestamp, ___Lake_datasource, ___Lake_sourcefile, ___Lake_isdeleted
)
WITH files AS (
    -- every Std file, numbered by download time
    SELECT ___Std_filename, ___Std_file_timestamp,
           row_number() OVER (ORDER BY ___Std_file_timestamp, ___Std_filename) AS file_seq
    FROM (
        SELECT DISTINCT ___Std_filename, ___Std_file_timestamp
        FROM hook.std_views.no_sodir_company_reserves
    )
),
observations AS (
    -- each key in each file, with its previous and next appearance
    SELECT r.*, f.file_seq,
           lag(r.___Std_md5) OVER k AS prev_md5,
           lag(f.file_seq)   OVER k AS prev_seq,
           lead(f.file_seq)  OVER k AS next_seq
    FROM hook.std_views.no_sodir_company_reserves r
    JOIN files f USING (___Std_filename, ___Std_file_timestamp)
    WINDOW k AS (
        PARTITION BY r.fldNpdidField, r.cmpNpdidCompany
        ORDER BY f.file_seq
    )
)
-- new, reappearing and changed rows
SELECT
    o.fldNpdidField, o.cmpNpdidCompany, o.cmpLongName, o.fldName, o.cmpRemainingOil,
    o.cmpRemainingGas, o.cmpRemainingNGL, o.cmpRemainingCondensate, o.cmpRemainingOE,
    o.cmpDateOffResEstDisplay, o.cmpShare, o.DatesyncNPD,
    o.___Std_md5, o.___Std_file_timestamp, 'no_sodir_company_reserves', o.___Std_filename, false
FROM observations o
WHERE o.prev_seq IS NULL                   -- first appearance
   OR o.prev_seq < o.file_seq - 1          -- reappears after being deleted
   OR o.prev_md5 <> o.___Std_md5           -- changed values
UNION ALL
-- deletion rows: the key is missing from the next file
SELECT
    o.fldNpdidField, o.cmpNpdidCompany, o.cmpLongName, o.fldName, o.cmpRemainingOil,
    o.cmpRemainingGas, o.cmpRemainingNGL, o.cmpRemainingCondensate, o.cmpRemainingOE,
    o.cmpDateOffResEstDisplay, o.cmpShare, o.DatesyncNPD,
    o.___Std_md5, nf.___Std_file_timestamp, 'no_sodir_company_reserves', nf.___Std_filename, true
FROM observations o
JOIN files nf ON nf.file_seq = o.file_seq + 1
WHERE o.next_seq IS NULL OR o.next_seq > o.file_seq + 1;
