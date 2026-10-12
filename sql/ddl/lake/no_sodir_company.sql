-- Lake table: Sodir companies (append-only change log).
-- Business key: cmpNpdidCompany
-- Loaded by sql/lake/no_sodir/company_{full,incremental}.sql.
--
-- Data columns: same names, order and types as the std view
-- hook.std_views.no_sodir_company. A change of dateSyncNPD alone makes no new row
-- (not in the MD5): each row keeps the values of the file it was observed
-- in. Lake metadata columns:
--   ___Lake_md5             MD5 of the non-key columns (the std view's ___Std_md5)
--   ___Lake_load_timestamp  when the change was observed: the source file's
--                           download time (UTC), not the insert time
--   ___Lake_datasource      dataset code (hook.metadata.datasets.code)
--   ___Lake_sourcefile      S3 path of the Std file the change was detected in
--   ___Lake_isdeleted       true: the key disappeared from that file (the row
--                           repeats its last known values)
CREATE SCHEMA IF NOT EXISTS lake.no_sodir;

CREATE TABLE IF NOT EXISTS lake.no_sodir.company (
    cmpNpdidCompany                     BIGINT,
    cmpLongName                         VARCHAR,
    cmpOrgNumberBrReg                   VARCHAR,
    cmpShortName                        VARCHAR,
    cmpNationCode                       VARCHAR,
    cmpSurveyPrefix                     VARCHAR,
    cmpLicenceOperCurrent               BOOLEAN,
    cmpLicenceOperFormer                BOOLEAN,
    cmpLicenceLicenseeCurrent           BOOLEAN,
    cmpLicenceLicenseeFormer            BOOLEAN,
    cmpTufOperCurrent                   BOOLEAN,
    cmpTufOperFormer                    BOOLEAN,
    cmpTufPartnerCurrent                BOOLEAN,
    cmpTufPartnerFormer                 BOOLEAN,
    cmpBsnsArrAreaOperCurrent           BOOLEAN,
    cmpBsnsArrAreaOperFormer            BOOLEAN,
    cmpBsnsArrAreaPartnerCurrent        BOOLEAN,
    cmpBsnsArrAreaPartnerFormer         BOOLEAN,
    dateSyncNPD                         DATE,
    ___Lake_md5                         VARCHAR,
    ___Lake_load_timestamp              TIMESTAMPTZ,
    ___Lake_datasource                  VARCHAR,
    ___Lake_sourcefile                  VARCHAR,
    ___Lake_isdeleted                   BOOLEAN
);
