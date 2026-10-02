-- Incremental-load state. Append-only: one row per successful load.
CREATE TABLE IF NOT EXISTS hook.metadata.watermark (
    source              VARCHAR,
    dataset             VARCHAR,
    load_mode           VARCHAR,      -- 'full' | 'incremental'
    last_period_fetched VARCHAR,      -- 'YYYY-MM'
    status              VARCHAR,
    raw_file            VARCHAR,      -- key in s3://hydroc-raw/
    updated_at          TIMESTAMPTZ
);

CREATE VIEW IF NOT EXISTS hook.metadata.watermark_latest AS
SELECT *
FROM hook.metadata.watermark
QUALIFY row_number() OVER (PARTITION BY source, dataset ORDER BY updated_at DESC) = 1;
