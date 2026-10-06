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
CREATE OR REPLACE TABLE hook.metadata.hooks AS
    FROM read_csv('s3://hydroc-raw/metadata/hooks/hooks.csv');
