-- Library views (production): Sodir field descriptions.
-- Frame:  library.frame.no_sodir_field_description   every version (SCD2)
-- Latest: library.latest.no_sodir_field_description  current versions only
-- Source: lake.no_sodir.field_description (one Lake table, no joins).
-- Business key: fldNpdidField, fldDescriptionHeading
--
-- Hooks (data/static/hooks.csv), production mode: BLOB
-- key_set_binary || <hook_expression_prod encoded per hook_encoding>
--   HK_FIELD  hook 7  key_set no_sodir.sup.field (0x080101)  expression fldNpdidField
--             encoding integer: 4 bytes, unsigned big-endian, 7 bytes in all
--
-- Frame columns: the hooks, the Lake table's data columns, its lineage
-- columns (___Lake_md5, ___Lake_datasource, ___Lake_sourcefile), then
--   ___Effective_From  when this version was observed (___Lake_load_timestamp)
--   ___Effective_To    when the next version of the key was observed;
--                      'infinity' for the key's last version (no time zone,
--                      so the same in every session: query open versions
--                      with ___Effective_To = 'infinity'::TIMESTAMPTZ)
--   ___Is_Deleted      true: the key disappeared at ___Effective_From
--
-- CREATE OR REPLACE: the definition must follow the repository. Fails at
-- server start while the Lake table doesn't exist; storage/lake.py re-runs
-- this script after every Lake load.
CREATE OR REPLACE VIEW library.frame.no_sodir_field_description AS
SELECT
    '\x08\x01\x01'::BLOB || unhex(printf('%08x', (fldNpdidField)::UINTEGER))  AS HK_FIELD,
    fldNpdidField,
    fldDescriptionHeading,
    fldName,
    fldDescriptionText,
    fldDescriptionDateUpdated,
    DatesyncNPD,
    ___Lake_md5,
    ___Lake_datasource,
    ___Lake_sourcefile,
    ___Lake_load_timestamp                                          AS ___Effective_From,
    lead(___Lake_load_timestamp, 1, 'infinity'::TIMESTAMPTZ) OVER (
        PARTITION BY fldNpdidField, fldDescriptionHeading
        ORDER BY ___Lake_load_timestamp
    )                                                               AS ___Effective_To,
    ___Lake_isdeleted                                               AS ___Is_Deleted
FROM lake.no_sodir.field_description;

CREATE OR REPLACE VIEW library.latest.no_sodir_field_description AS
SELECT * EXCLUDE (___Effective_From, ___Effective_To, ___Is_Deleted)
FROM library.frame.no_sodir_field_description
WHERE ___Effective_To = 'infinity'::TIMESTAMPTZ
  AND NOT ___Is_Deleted;
