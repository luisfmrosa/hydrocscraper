-- Objects supporting the Hook methodology (sources, datasets, business concepts...).
CREATE SCHEMA IF NOT EXISTS hook.metadata;
-- Views mapping files stored in the Raw bucket.
CREATE SCHEMA IF NOT EXISTS hook.raw_views;
-- Views mapping the Parquet files of the Std bucket (what the Lake loads from).
CREATE SCHEMA IF NOT EXISTS hook.std_views;
