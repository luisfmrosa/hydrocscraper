---
name: std-view
description: Write the std view (hook.std_views.<code>) over one Std table's Parquet files in hydroc-std, with the ___Std_* metadata columns (MD5 of the non-key columns, file name, period, timestamp) that the Lake loads read. Use when adding a dataset or flattened table to hydrocscraper, after its Std script exists.
---

# Std view for a Std table

Input: a row of `data/static/datasets.csv` **with keys**: its `code` (`<source>_<dataset>`, or `<source>_<dataset>_<sub_table>` for a flattened table) and `keys`. Its Std script (`std-script` skill) must exist. Below, `<table>` is the code without `<source>_`.

**Worked example (tested):** `sql/ddl/std_views/020_no_sodir_field_production_monthly.sql`.

## Conventions

- **File:** `sql/ddl/std_views/<nnn>_<code>.sql`, `<nnn>` being the next free number; the runner finds it with the glob `*_<code>.sql`, so exactly one file must match.
- **Object:** `CREATE OR REPLACE VIEW hook.std_views.<code>`.
- **Source:** `read_parquet('s3://hydroc-std/<source>/<table>/*/*.parquet', hive_partitioning = true, filename = true, union_by_name = true)`.
- **Data columns:** list them explicitly, in the order the Std script writes them (keys first, `parent` first for a nested sub-table). No casts: the Parquet files are already typed. Never `SELECT *`. The Lake table has the same names, order and types.
- **Metadata columns,** at the end, in this order:

| Column | Expression |
|---|---|
| `___Std_md5` | `md5(concat_ws(chr(31), coalesce(<col>::VARCHAR, ''), …))` over **every non-key column**, in view order |
| `___Std_filename` | `filename` |
| `___Std_year_month` | `year_month::VARCHAR` |
| `___Std_file_timestamp` | `strptime(regexp_extract(filename, '_(\d{8}_\d{4})\.[^./]+$', 1) \|\| ' +0000', '%Y%m%d_%H%M %z')` |

The timestamp is the Raw file's (the Std script keeps it), so it is when the data was received.

- Add a header comment: table, business key, which scripts load it into the Lake, and the meaning of the metadata columns, as in the example.

## Register and verify

1. Add `.read std_views/<nnn>_<code>.sql` to `sql/ddl/init_server.sql`, under the raw views.
2. On the Docker stack: `docker compose restart duckdb`; "No files found" is expected until the first Std file exists (the app re-creates the view before each Lake load).
3. After a full load, check counts and key uniqueness per file:
   ```sql
   SELECT count(*), count(DISTINCT ___Std_filename) FROM hook.std_views.<code>;
   SELECT ___Std_filename, <keys>, count(*) FROM hook.std_views.<code> GROUP BY ALL HAVING count(*) > 1;  -- must be empty
   ```
4. Keys must never be NULL: `SELECT count(*) FROM hook.std_views.<code> WHERE <key> IS NULL OR …` must return 0. If the source can't guarantee it, raise it with the user (and add the check to the Std script).
5. Flattened sub-table: no orphans. Every `parent` must exist in the parent table's file with the same timestamp:
   ```sql
   SELECT count(*) FROM hook.std_views.<code> c
   WHERE NOT EXISTS (
       SELECT 1 FROM hook.std_views.<parent_code> p
       WHERE p.___Std_file_timestamp = c.___Std_file_timestamp
         AND concat_ws(chr(31), <parent key columns>::VARCHAR) = c.parent
   )
   ```
   This must return 0.
