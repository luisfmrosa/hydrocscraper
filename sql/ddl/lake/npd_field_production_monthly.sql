-- Lake table: NPD monthly field production (append-only change log).
-- Business key: prfNpdidInformationCarrier, prfYear, prfMonth
-- Loaded by sql/lake/npd/field_production_monthly_{full,incremental}.sql.
--
-- Data columns: same names, order and types as the std view
-- hook.std_views.npd_field_production_monthly. Lake metadata columns:
--   ___Lake_md5             MD5 of the non-key columns (the std view's ___Std_md5)
--   ___Lake_load_timestamp  when the change was observed: the source file's
--                           download time (UTC), not the insert time
--   ___Lake_datasource      dataset code (hook.metadata.datasets.code)
--   ___Lake_sourcefile      S3 path of the Std file the change was detected in
--   ___Lake_isdeleted       true: the key disappeared from that file (the row
--                           repeats its last known values)
CREATE SCHEMA IF NOT EXISTS lake.npd;

CREATE TABLE IF NOT EXISTS lake.npd.field_production_monthly (
    prfNpdidInformationCarrier          BIGINT,
    prfYear                             INTEGER,
    prfMonth                            INTEGER,
    prfInformationCarrier               VARCHAR,
    prfPrdOilNetMillSm3                 DOUBLE,
    prfPrdGasNetBillSm3                 DOUBLE,
    prfPrdNGLNetMillSm3                 DOUBLE,
    prfPrdCondensateNetMillSm3          DOUBLE,
    prfPrdOeNetMillSm3                  DOUBLE,
    prfPrdProducedWaterInFieldMillSm3   DOUBLE,
    ___Lake_md5                         VARCHAR,
    ___Lake_load_timestamp              TIMESTAMPTZ,
    ___Lake_datasource                  VARCHAR,
    ___Lake_sourcefile                  VARCHAR,
    ___Lake_isdeleted                   BOOLEAN
);
