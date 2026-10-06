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
.read 45_hook_static.sql

-- Lake tables, one script per dataset
.read lake/no_sodir_field_production_monthly.sql

-- Raw and std views fail while their S3 prefix is still empty ("No files
-- found"). With bail off the server still starts; the app re-runs the raw
-- view before every Std step and the std view before every Lake load.
.read raw_views/020_no_sodir_field_production_monthly.sql
.read std_views/020_no_sodir_field_production_monthly.sql

-- Library frame and latest views, one script per Lake table and mode
-- (<code>.sql production, <code>_dev.sql development). They fail until the
-- Lake table exists; the app re-runs them after every Lake load.
.read library/no_sodir_field_production_monthly_dev.sql

.read 99_serve.sql
