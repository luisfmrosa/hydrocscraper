-- Library views (production): Sodir monthly field production.
-- Frame:  library.frame.no_sodir_field_production_monthly   every version (SCD2)
-- Latest: library.latest.no_sodir_field_production_monthly  current versions only
-- Source: lake.no_sodir.field_production_monthly (one Lake table, no joins).
-- Business key: prfNpdidInformationCarrier, prfYear, prfMonth
--
-- Hooks (data/static/hooks.csv), production mode: BLOB
-- key_set_binary || <hook_expression_prod encoded per hook_encoding>
--   HK_FIELD  hook 1  key_set no_sodir.field (0x0801)  expression prfNpdidInformationCarrier
--             encoding integer: 4 bytes, unsigned big-endian, so 6 bytes in
--             all (43437 -> 0x08010000A9AD); a negative or too large NPDID
--             fails the cast instead of building a wrong hook
-- prfNpdidInformationCarrier also holds discoveries in test production
-- (e.g. 16/1-12 Troldhaugen): hooked as field too, with no row in the
-- fields dataset (no_sodir_field).
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
CREATE OR REPLACE VIEW library.frame.no_sodir_field_production_monthly AS
SELECT
    '\x08\x01'::BLOB || unhex(printf('%08x', (prfNpdidInformationCarrier)::UINTEGER))  AS HK_FIELD,
    prfNpdidInformationCarrier,
    prfYear,
    prfMonth,
    prfInformationCarrier,
    prfPrdOilNetMillSm3,
    prfPrdGasNetBillSm3,
    prfPrdNGLNetMillSm3,
    prfPrdCondensateNetMillSm3,
    prfPrdOeNetMillSm3,
    prfPrdProducedWaterInFieldMillSm3,
    ___Lake_md5,
    ___Lake_datasource,
    ___Lake_sourcefile,
    ___Lake_load_timestamp                                          AS ___Effective_From,
    lead(___Lake_load_timestamp, 1, 'infinity'::TIMESTAMPTZ) OVER (
        PARTITION BY prfNpdidInformationCarrier, prfYear, prfMonth
        ORDER BY ___Lake_load_timestamp
    )                                                               AS ___Effective_To,
    ___Lake_isdeleted                                               AS ___Is_Deleted
FROM lake.no_sodir.field_production_monthly;

CREATE OR REPLACE VIEW library.latest.no_sodir_field_production_monthly AS
SELECT * EXCLUDE (___Effective_From, ___Effective_To, ___Is_Deleted)
FROM library.frame.no_sodir_field_production_monthly
WHERE ___Effective_To = 'infinity'::TIMESTAMPTZ
  AND NOT ___Is_Deleted;
