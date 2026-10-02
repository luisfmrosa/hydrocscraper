-- One DuckLake per layer. The ducklake_<layer> secrets (catalog in Postgres
-- cat_hydroc_<layer>, data in s3://hydroc-<layer>/) come from secrets.sql.
-- Aliases are fixed: cross-layer views reference objects by these names.
ATTACH IF NOT EXISTS 'ducklake:ducklake_lake' AS lake;
ATTACH IF NOT EXISTS 'ducklake:ducklake_library' AS library;
ATTACH IF NOT EXISTS 'ducklake:ducklake_dwh' AS dwh;
ATTACH IF NOT EXISTS 'ducklake:ducklake_hook' AS hook;
