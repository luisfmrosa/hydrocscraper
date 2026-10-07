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

COPY (FROM read_csv('/opt/duckdb/static/business_domains.csv'))
    TO 's3://hydroc-raw/metadata/business_domains/business_domains.csv' (HEADER);
-- Business domains group business concepts. code: exactly 3 lowercase letters
-- or digits (it becomes part of key_set); id: one byte of key_set_binary.
-- Any invalid row (duplicate id or code, bad code, empty name, id above 255)
-- fails the statement, so the previous table is kept and the error shows in
-- the server log.
CREATE OR REPLACE TABLE hook.metadata.business_domains AS
WITH d AS (
    SELECT
        id::INTEGER                                         AS id,
        trim(code)                                          AS code,
        nullif(trim(name), '')                              AS name,
        description,
        count(*) OVER (PARTITION BY id::INTEGER)            AS id_count,
        count(*) OVER (PARTITION BY trim(code))             AS code_count
    FROM read_csv('s3://hydroc-raw/metadata/business_domains/business_domains.csv', all_varchar = true)
)
SELECT
    CASE
        WHEN id IS NULL
            THEN error('business_domains.csv: empty id')
        WHEN id_count > 1
            THEN error('business_domains.csv: duplicate id ' || id)
        WHEN id NOT BETWEEN 0 AND 255
            THEN error('business_domains.csv id ' || id || ': must fit in one byte (0-255) for key_set_binary')
        ELSE id
    END                                                     AS id,
    CASE
        WHEN code IS NULL OR NOT regexp_full_match(code, '[a-z0-9]{3}')
            THEN error('business_domains.csv id ' || id || ': code ' || coalesce(code, '(empty)')
                       || ' must be exactly 3 lowercase letters or digits')
        WHEN code_count > 1
            THEN error('business_domains.csv: duplicate code ' || code)
        ELSE code
    END                                                     AS code,
    CASE
        WHEN name IS NULL
            THEN error('business_domains.csv id ' || id || ': empty name')
        ELSE name
    END                                                     AS name,
    description
FROM d
ORDER BY 1;

COPY (FROM read_csv('/opt/duckdb/static/business_concepts.csv'))
    TO 's3://hydroc-raw/metadata/business_concepts/business_concepts.csv' (HEADER);
-- Every business concept belongs to one business domain. Its id is unique
-- across domains, so the domain adds no uniqueness to a hook; but the domain
-- is part of every hook of the concept (key_set, key_set_binary), so a
-- concept's domain must never change once a hook uses it (create a new
-- concept instead). Any invalid row (duplicate id or code, empty code, missing
-- or unknown business_domain_id) fails the statement.
CREATE OR REPLACE TABLE hook.metadata.business_concepts AS
WITH c AS (
    SELECT
        c.id::INTEGER                                       AS id,
        nullif(trim(c.code), '')                            AS code,
        c.name,
        c.description,
        c.business_domain_id::INTEGER                       AS business_domain_id,
        count(*) OVER (PARTITION BY c.id::INTEGER)          AS id_count,
        count(*) OVER (PARTITION BY trim(c.code))           AS code_count,
        bd.id                                               AS bd_id
    FROM read_csv('s3://hydroc-raw/metadata/business_concepts/business_concepts.csv', all_varchar = true) c
    LEFT JOIN hook.metadata.business_domains bd ON bd.id = c.business_domain_id::INTEGER
)
SELECT
    CASE
        WHEN id IS NULL
            THEN error('business_concepts.csv: empty id')
        WHEN id_count > 1
            THEN error('business_concepts.csv: duplicate id ' || id)
        ELSE id
    END                                                     AS id,
    CASE
        WHEN code IS NULL
            THEN error('business_concepts.csv id ' || id || ': empty code')
        WHEN code_count > 1
            THEN error('business_concepts.csv: duplicate code ' || code)
        ELSE code
    END                                                     AS code,
    name,
    description,
    CASE
        WHEN business_domain_id IS NULL
            THEN error('business_concepts.csv id ' || id || ': empty business_domain_id')
        WHEN bd_id IS NULL
            THEN error('business_concepts.csv id ' || id || ': unknown business_domain_id ' || business_domain_id)
        ELSE business_domain_id
    END                                                     AS business_domain_id
FROM c
ORDER BY 1;

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
--   key_set         <source code>.<business domain code>.<business concept code>
--                   (e.g. no_sodir.sup.field)
--   key_set_binary  source id (1 byte) || business domain id (1 byte)
--                   || business concept id (1 byte) (e.g. 0x080101); ids
--                   above 255 are rejected
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
        bc.code                                             AS bc_code,
        bd.id                                               AS bd_id,
        bd.code                                             AS bd_code
    FROM read_csv('s3://hydroc-raw/metadata/hooks/hooks.csv', all_varchar = true) h
    LEFT JOIN hook.metadata.datasets d ON d.id = h.dataset_id::INTEGER
    LEFT JOIN hook.metadata.sources s ON s.id = d.source_id
    LEFT JOIN hook.metadata.business_concepts bc ON bc.id = h.business_concept_id::INTEGER
    LEFT JOIN hook.metadata.business_domains bd ON bd.id = bc.business_domain_id
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
            ELSE s_code || '.' || bd_code || '.' || bc_code
        END                                                 AS key_set,
        CASE
            WHEN s_id NOT BETWEEN 0 AND 255 OR bd_id NOT BETWEEN 0 AND 255 OR bc_id NOT BETWEEN 0 AND 255
                THEN error('hooks.csv id ' || id || ': source id ' || s_id || ', business domain id ' || bd_id
                           || ' and business concept id ' || bc_id
                           || ' must fit in one byte (0-255) for key_set_binary')
            ELSE unhex(printf('%02x', s_id)) || unhex(printf('%02x', bd_id)) || unhex(printf('%02x', bc_id))
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
