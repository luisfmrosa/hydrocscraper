-- Static Hook metadata, maintained in the repository under data/static/ and
-- mounted (Docker) or copied (Incus) to /opt/duckdb/static on the server.
-- Each start copies every file to s3://hydroc-raw/metadata/<name>/<name>.csv
-- and rebuilds hook.metadata.<name> from that copy. CREATE OR REPLACE (not
-- IF NOT EXISTS): the content is static and must follow the repository.

COPY (FROM read_csv('/opt/duckdb/static/sources.csv'))
    TO 's3://hydroc-raw/metadata/sources/sources.csv' (HEADER);
CREATE OR REPLACE TABLE hook.metadata.sources AS
    FROM read_csv('s3://hydroc-raw/metadata/sources/sources.csv');

COPY (FROM read_csv('/opt/duckdb/static/datasets.csv'))
    TO 's3://hydroc-raw/metadata/datasets/datasets.csv' (HEADER);
CREATE OR REPLACE TABLE hook.metadata.datasets AS
    FROM read_csv('s3://hydroc-raw/metadata/datasets/datasets.csv');

COPY (FROM read_csv('/opt/duckdb/static/business_concepts.csv'))
    TO 's3://hydroc-raw/metadata/business_concepts/business_concepts.csv' (HEADER);
CREATE OR REPLACE TABLE hook.metadata.business_concepts AS
    FROM read_csv('s3://hydroc-raw/metadata/business_concepts/business_concepts.csv');

COPY (FROM read_csv('/opt/duckdb/static/hooks.csv'))
    TO 's3://hydroc-raw/metadata/hooks/hooks.csv' (HEADER);
-- Hooks: hooks.csv holds id, business_concept_id, dataset_id and, for the
-- business key, one SQL expression over the dataset's columns per mode of the
-- Library views, plus the production encoding:
--   hook_expression_dev   development hook value, used as text (e.g. a name:
--                         prfInformationCarrier)
--   hook_expression_prod  production hook value (e.g. an id:
--                         prfNpdidInformationCarrier)
--   hook_encoding         how the production value is encoded after
--                         key_set_binary (big-endian, unsigned: a negative
--                         or too large value fails the view):
--                           integer  4 bytes (0 to 4,294,967,295)
--                           bigint   8 bytes (empty = bigint)
--                           varchar  UTF-8 text
-- The hook identifiers are derived here, so they always follow the
-- referenced rows:
--   key_set         <source code>.<business concept code>   (e.g. no_sodir.field)
--   key_set_binary  source id (1 byte) || business concept id (1 byte)
--                   (e.g. 0x0801); ids above 255 are rejected
-- Hooks of the same key set must share an encoding, or their production
-- values could never match. Any invalid row (duplicate id, unknown dataset or
-- business concept, empty expression, unknown encoding, mixed encodings in a
-- key set, id above 255) fails the statement, so the previous table is kept
-- and the error shows in the server log.
CREATE OR REPLACE TABLE hook.metadata.hooks AS
WITH h AS (
    SELECT
        h.id::INTEGER                                       AS id,
        h.business_concept_id::INTEGER                      AS business_concept_id,
        h.dataset_id::INTEGER                               AS dataset_id,
        nullif(trim(h.hook_expression_dev::VARCHAR), '')    AS hook_expression_dev,
        nullif(trim(h.hook_expression_prod::VARCHAR), '')   AS hook_expression_prod,
        coalesce(lower(nullif(trim(h.hook_encoding::VARCHAR), '')), 'bigint') AS hook_encoding,
        count(*) OVER (PARTITION BY h.id)                   AS id_count,
        d.id                                                AS d_id,
        d.code                                              AS d_code,
        s.id                                                AS s_id,
        s.code                                              AS s_code,
        bc.id                                               AS bc_id,
        bc.code                                             AS bc_code
    FROM read_csv('s3://hydroc-raw/metadata/hooks/hooks.csv', all_varchar = true) h
    LEFT JOIN hook.metadata.datasets d ON d.id = h.dataset_id::INTEGER
    LEFT JOIN hook.metadata.sources s ON s.id = d.source_id
    LEFT JOIN hook.metadata.business_concepts bc ON bc.id = h.business_concept_id::INTEGER
),
checked AS (
    SELECT
        id,
        business_concept_id,
        dataset_id,
        CASE
            WHEN hook_expression_dev IS NULL
                THEN error('hooks.csv id ' || id || ': empty hook_expression_dev')
            ELSE hook_expression_dev
        END                                                 AS hook_expression_dev,
        CASE
            WHEN hook_expression_prod IS NULL
                THEN error('hooks.csv id ' || id || ': empty hook_expression_prod')
            ELSE hook_expression_prod
        END                                                 AS hook_expression_prod,
        CASE
            WHEN hook_encoding NOT IN ('integer', 'bigint', 'varchar')
                THEN error('hooks.csv id ' || id || ': unknown hook_encoding ' || hook_encoding
                           || ' (integer, bigint or varchar)')
            ELSE hook_encoding
        END                                                 AS hook_encoding,
        CASE
            WHEN id_count > 1
                THEN error('hooks.csv: duplicate id ' || id)
            WHEN d_id IS NULL
                THEN error('hooks.csv id ' || id || ': unknown dataset_id ' || dataset_id)
            WHEN s_id IS NULL
                THEN error('hooks.csv id ' || id || ': dataset ' || d_code || ' has an unknown source_id')
            WHEN bc_id IS NULL
                THEN error('hooks.csv id ' || id || ': unknown business_concept_id ' || business_concept_id)
            ELSE s_code || '.' || bc_code
        END                                                 AS key_set,
        CASE
            WHEN s_id NOT BETWEEN 0 AND 255 OR bc_id NOT BETWEEN 0 AND 255
                THEN error('hooks.csv id ' || id || ': source id ' || s_id || ' and business concept id '
                           || bc_id || ' must fit in one byte (0-255) for key_set_binary')
            ELSE unhex(printf('%02x', s_id)) || unhex(printf('%02x', bc_id))
        END                                                 AS key_set_binary
    FROM h
)
SELECT
    id, business_concept_id, dataset_id, hook_expression_dev, hook_expression_prod,
    CASE
        WHEN min(hook_encoding) OVER (PARTITION BY key_set) <> max(hook_encoding) OVER (PARTITION BY key_set)
            THEN error('hooks.csv id ' || id || ': key set ' || key_set
                       || ' has hooks with different hook_encoding')
        ELSE hook_encoding
    END                                                     AS hook_encoding,
    key_set,
    key_set_binary
FROM checked
ORDER BY id;
