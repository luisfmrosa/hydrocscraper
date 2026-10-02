-- Every discovery snapshot; the snapshot timestamp is taken from the filename.
CREATE VIEW IF NOT EXISTS hook.raw_views.known_sources AS
SELECT
    *,
    strptime(regexp_extract(filename, 'known_sources_(\d{8}_\d{4})\.json$', 1), '%Y%m%d_%H%M') AS snapshot_at
FROM read_json('s3://hydroc-raw/metadata/known_sources/*.json', filename = true, union_by_name = true);
