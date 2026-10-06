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
-- Hooks: hooks.csv holds id, business_concept_id, dataset_id and
-- hook_expression (SQL over the dataset's std view columns that gives the
-- business key, e.g. prfNpdidInformationCarrier). The hook identifiers are
-- derived here, so they always follow the referenced rows:
--   key_set         <source code>.<business concept code>   (e.g. npd.field)
--   key_set_binary  source id (1 byte) || business concept id (1 byte)
--                   (e.g. 0x0801); ids above 255 are rejected
-- Any invalid row (duplicate id, unknown dataset or business concept, empty
-- hook_expression, id above 255) fails the statement, so the previous table is kept and the
-- error shows in the server log.
CREATE OR REPLACE TABLE hook.metadata.hooks AS
SELECT
    h.id::INTEGER                                   AS id,
    h.business_concept_id::INTEGER                  AS business_concept_id,
    h.dataset_id::INTEGER                           AS dataset_id,
    CASE
        WHEN nullif(trim(h.hook_expression::VARCHAR), '') IS NULL
            THEN error('hooks.csv id ' || h.id || ': empty hook_expression')
        ELSE trim(h.hook_expression::VARCHAR)
    END                                             AS hook_expression,
    CASE
        WHEN count(*) OVER (PARTITION BY h.id) > 1
            THEN error('hooks.csv: duplicate id ' || h.id)
        WHEN d.id IS NULL
            THEN error('hooks.csv id ' || h.id || ': unknown dataset_id ' || h.dataset_id)
        WHEN s.id IS NULL
            THEN error('hooks.csv id ' || h.id || ': dataset ' || d.code || ' has an unknown source_id')
        WHEN bc.id IS NULL
            THEN error('hooks.csv id ' || h.id || ': unknown business_concept_id ' || h.business_concept_id)
        ELSE s.code || '.' || bc.code
    END                                             AS key_set,
    CASE
        WHEN s.id NOT BETWEEN 0 AND 255 OR bc.id NOT BETWEEN 0 AND 255
            THEN error('hooks.csv id ' || h.id || ': source id ' || s.id || ' and business concept id '
                       || bc.id || ' must fit in one byte (0-255) for key_set_binary')
        ELSE unhex(printf('%02x', s.id)) || unhex(printf('%02x', bc.id))
    END                                             AS key_set_binary
FROM read_csv('s3://hydroc-raw/metadata/hooks/hooks.csv') h
LEFT JOIN hook.metadata.datasets d ON d.id = h.dataset_id
LEFT JOIN hook.metadata.sources s ON s.id = d.source_id
LEFT JOIN hook.metadata.business_concepts bc ON bc.id = h.business_concept_id
ORDER BY h.id;
