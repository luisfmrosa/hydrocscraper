-- Library views (production): Sodir companies.
-- Frame:  library.frame.no_sodir_company   every version (SCD2)
-- Latest: library.latest.no_sodir_company  current versions only
-- Source: lake.no_sodir.company (one Lake table, no joins).
-- Business key: cmpNpdidCompany
--
-- Hooks (data/static/hooks.csv), production mode: BLOB
-- key_set_binary || <hook_expression_prod encoded per hook_encoding>
--   HK_COMPANY  hook 4  key_set no_sodir.sup.cmp (0x080102)  expression cmpNpdidCompany
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
CREATE OR REPLACE VIEW library.frame.no_sodir_company AS
SELECT
    '\x08\x01\x02'::BLOB || unhex(printf('%08x', (cmpNpdidCompany)::UINTEGER))  AS HK_COMPANY,
    cmpNpdidCompany,
    cmpLongName,
    cmpOrgNumberBrReg,
    cmpShortName,
    cmpNationCode,
    cmpSurveyPrefix,
    cmpLicenceOperCurrent,
    cmpLicenceOperFormer,
    cmpLicenceLicenseeCurrent,
    cmpLicenceLicenseeFormer,
    cmpTufOperCurrent,
    cmpTufOperFormer,
    cmpTufPartnerCurrent,
    cmpTufPartnerFormer,
    cmpBsnsArrAreaOperCurrent,
    cmpBsnsArrAreaOperFormer,
    cmpBsnsArrAreaPartnerCurrent,
    cmpBsnsArrAreaPartnerFormer,
    dateSyncNPD,
    ___Lake_md5,
    ___Lake_datasource,
    ___Lake_sourcefile,
    ___Lake_load_timestamp                                          AS ___Effective_From,
    lead(___Lake_load_timestamp, 1, 'infinity'::TIMESTAMPTZ) OVER (
        PARTITION BY cmpNpdidCompany
        ORDER BY ___Lake_load_timestamp
    )                                                               AS ___Effective_To,
    ___Lake_isdeleted                                               AS ___Is_Deleted
FROM lake.no_sodir.company;

CREATE OR REPLACE VIEW library.latest.no_sodir_company AS
SELECT * EXCLUDE (___Effective_From, ___Effective_To, ___Is_Deleted)
FROM library.frame.no_sodir_company
WHERE ___Effective_To = 'infinity'::TIMESTAMPTZ
  AND NOT ___Is_Deleted;
