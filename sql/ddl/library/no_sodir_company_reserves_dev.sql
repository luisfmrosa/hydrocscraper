-- Library views (development): Sodir company reserves.
-- Frame:  library.frame.no_sodir_company_reserves_dev   every version (SCD2)
-- Latest: library.latest.no_sodir_company_reserves_dev  current versions only
-- Source: lake.no_sodir.company_reserves (one Lake table, no joins).
-- Business key: fldNpdidField, cmpNpdidCompany
--
-- Hooks (data/static/hooks.csv), development mode: VARCHAR
-- '<key_set>|<hook_expression_dev>'
--   HK_COMPANY  hook 5  key_set no_sodir.sup.cmp  expression cmpLongName
-- (the licensee company's name)
--   HK_FIELD  hook 6  key_set no_sodir.sup.field  expression fldName
-- (the field's name)
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
CREATE OR REPLACE VIEW library.frame.no_sodir_company_reserves_dev AS
SELECT
    'no_sodir.sup.cmp' || '|' || (cmpLongName)::VARCHAR             AS HK_COMPANY,
    'no_sodir.sup.field' || '|' || (fldName)::VARCHAR               AS HK_FIELD,
    fldNpdidField,
    cmpNpdidCompany,
    cmpLongName,
    fldName,
    cmpRemainingOil,
    cmpRemainingGas,
    cmpRemainingNGL,
    cmpRemainingCondensate,
    cmpRemainingOE,
    cmpDateOffResEstDisplay,
    cmpShare,
    DatesyncNPD,
    ___Lake_md5,
    ___Lake_datasource,
    ___Lake_sourcefile,
    ___Lake_load_timestamp                                          AS ___Effective_From,
    lead(___Lake_load_timestamp, 1, 'infinity'::TIMESTAMPTZ) OVER (
        PARTITION BY fldNpdidField, cmpNpdidCompany
        ORDER BY ___Lake_load_timestamp
    )                                                               AS ___Effective_To,
    ___Lake_isdeleted                                               AS ___Is_Deleted
FROM lake.no_sodir.company_reserves;

CREATE OR REPLACE VIEW library.latest.no_sodir_company_reserves_dev AS
SELECT * EXCLUDE (___Effective_From, ___Effective_To, ___Is_Deleted)
FROM library.frame.no_sodir_company_reserves_dev
WHERE ___Effective_To = 'infinity'::TIMESTAMPTZ
  AND NOT ___Is_Deleted;
