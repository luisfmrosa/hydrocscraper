-- DuckDB quack server startup script.
-- Run by systemd as:  duckdb -init init_server.sql  (working directory: this folder)
-- Every object is created with IF NOT EXISTS, so each (re)start is safe.
-- Credentials live only in /opt/duckdb/secrets.sql, rendered by Ansible.

-- The CLI aborts an -init file on the first error unless bail is off.
.bail off

.read 00_extensions.sql
.read /opt/duckdb/secrets.sql
.read 10_attach.sql
.read 20_library.sql
.read 30_dwh.sql
.read 40_hook.sql
.read 41_hook_watermark.sql

-- Raw views fail while their S3 prefix is still empty ("No files found").
-- With bail off the server still starts; restart the service once data exists.
.read raw_views/010_known_sources.sql
.read raw_views/020_npd_field_production_monthly.sql

.read 99_serve.sql
