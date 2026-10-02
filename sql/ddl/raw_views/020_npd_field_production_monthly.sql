CREATE VIEW IF NOT EXISTS hook.raw_views.npd_field_production_monthly AS
SELECT *
FROM read_csv(
    's3://hydroc-raw/npd/field_production_monthly/*/*.csv',
    hive_partitioning = true,
    filename = true,
    union_by_name = true
);
