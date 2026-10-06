---
name: lake-table
description: Write the static DDL of a Lake table (lake.<source>.<table>, one per Std table) — its data columns plus the five ___Lake_* columns. Use when adding a dataset or flattened table to hydrocscraper, after its std view exists, or when the std view's columns change.
---

# Lake table for a Std table

Input: a row of `data/static/datasets.csv` with keys and its `code`. Its std view (`std-view` skill) must already exist in `sql/ddl/std_views/`.

There is one Lake table per Std table:

| `code` | Lake table |
|---|---|
| `<source>_<dataset>` (tabular) | `lake.<source>.<dataset>` |
| `<source>_<dataset>_<sub_table>` (flattened) | `lake.<source>.<dataset>_<sub_table>` |

Below, `<table>` is the code without `<source>_`.

**Worked example (tested):** `sql/ddl/lake/no_sodir_field_production_monthly.sql`.

## Conventions

- **File:** `sql/ddl/lake/<code>.sql`.
- **Statements:**
  1. `CREATE SCHEMA IF NOT EXISTS lake.<source>;` (one schema per source)
  2. `CREATE TABLE IF NOT EXISTS lake.<source>.<table> (...)` with explicit columns. No `CREATE TABLE AS`.
- **Data columns:** exactly the std view's data columns, with the same names, order and types, keys first (`parent` first for a nested sub-table). Don't include the `___Std_*` columns.
- **Lake metadata columns,** at the end, in this order:

```sql
    ___Lake_md5                         VARCHAR,
    ___Lake_load_timestamp              TIMESTAMPTZ,
    ___Lake_datasource                  VARCHAR,
    ___Lake_sourcefile                  VARCHAR,
    ___Lake_isdeleted                   BOOLEAN
```

| Column | Meaning |
|---|---|
| `___Lake_md5` | The std view's `___Std_md5` (MD5 of the non-key columns) |
| `___Lake_load_timestamp` | When the change was observed: the file's `___Std_file_timestamp` (the Raw download time), not the insert time |
| `___Lake_datasource` | The row's `code` in `datasets.csv` |
| `___Lake_sourcefile` | The Std file's `___Std_filename` |
| `___Lake_isdeleted` | `true` when the key disappeared from that file |

- Add a header comment: table, business key, which scripts load it, and the meaning of the metadata columns, as in the example.

## Changing an existing table

`IF NOT EXISTS` never alters an existing table. If the columns change:
- **Added column:** add it to the DDL *and* write an `ALTER TABLE … ADD COLUMN IF NOT EXISTS …` in the same file, after the `CREATE`.
- **Changed type, removed or reordered column:** ask the user. The Lake is append-only history; the usual way out is `DROP TABLE` followed by a full load, which rebuilds Std from Raw and the Lake from Std.

## Register and verify

1. Add `.read lake/<code>.sql` to `sql/ddl/init_server.sql`, under `-- Lake tables`.
2. On the Docker stack: `docker compose restart duckdb`. The log must show no error for this file.
3. Compare the columns with the std view (names, order, types):
   ```sql
   SELECT column_name, data_type FROM information_schema.columns
   WHERE table_catalog = 'lake' AND table_schema = '<source>' AND table_name = '<table>'
   ORDER BY ordinal_position
   ```
