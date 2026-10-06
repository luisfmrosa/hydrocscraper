---
name: raw-view
description: Write the raw view (hook.raw_views.<source>_<dataset>) that maps a dataset's Raw files as received, with the ___Raw_* metadata columns, for its Std script to read. Use when adding a dataset to hydrocscraper or when a source file's columns change.
---

# Raw view for a dataset

Input: the dataset code `<source>_<dataset>` (e.g. `no_sodir_field_production_monthly`). Every dataset has exactly one raw view, whatever its shape: it maps the Raw files **as received** and is read only by the dataset's Std script (`std-script` skill). Typing, flattening and checks happen there, not here.

**Worked example (tested):** `sql/ddl/raw_views/020_no_sodir_field_production_monthly.sql`. Read it first and follow its structure.

## Which files it reads

`s3://hydroc-raw/<source>/<dataset>/*/<pattern>`, where `<pattern>` selects the files DuckDB reads:

| Source | Files in Raw | View reads |
|---|---|---|
| File DuckDB reads (CSV, TSV, xlsx, JSON, Parquet…) | as received | those files, e.g. `*.csv` |
| Legacy format (`.xls`, HTML) | as received + Parquet conversion (same timestamp) | only the conversions, `*.parquet` |
| Database table / SDK extract | Parquet extract | `*.parquet` |

## Conventions

- **File:** `sql/ddl/raw_views/<nnn>_<source>_<dataset>.sql`, where `<nnn>` is the next free number (010, 020, …). The runner finds it with the glob `*_<code>.sql`, so exactly one file must match.
- **Object:** `CREATE OR REPLACE VIEW hook.raw_views.<source>_<dataset>`. Use `OR REPLACE`, not `IF NOT EXISTS`: the definition must follow the repository.
- **Reader options:** always `hive_partitioning = true` and `filename = true`.
  - CSV/TSV: `read_csv(…, union_by_name = true, all_varchar = true)`. Text only: a value that doesn't cast must fail in the Std script, where it can be checked, not make the view unbindable.
  - Parquet: `read_parquet(…, union_by_name = true)`.
  - JSON: `read_json(…)`; nested structures stay nested (the Std script flattens them).
  - xlsx: `read_xlsx(…, all_varchar = true)` (excel extension); name the sheet if needed.
- **Data columns:** list every source column explicitly with its **original name**, without casts or renames. Never `SELECT *`: the list documents the file and makes a missing column fail loudly.
- **Metadata columns,** at the end, in this order:

| Column | Expression |
|---|---|
| `___Raw_filename` | `filename` |
| `___Raw_year_month` | `year_month::VARCHAR` |
| `___Raw_file_timestamp` | `strptime(regexp_extract(filename, '_(\d{8}_\d{4})\.[^./]+$', 1) \|\| ' +0000', '%Y%m%d_%H%M %z')` |

- No MD5 here: it belongs to the std view (`std-view` skill).
- Add a header comment: dataset, which Std script reads it, and the meaning of the metadata columns, as in the example.

## Register and verify

1. Add `.read raw_views/<nnn>_<code>.sql` to `sql/ddl/init_server.sql`, under the existing raw views.
2. On the Docker stack (`architecture/docker`): `docker compose restart duckdb`, then check `docker compose logs duckdb` for errors. "No files found" is expected until the dataset has files.
3. Check the view:
   ```bash
   docker compose run --rm app python -c "from storage import duck; print(duck.query('SELECT count(*), count(DISTINCT ___Raw_filename), min(___Raw_file_timestamp) FROM hook.raw_views.<code>')[1])"
   ```
4. A filter on `___Raw_filename` must read only that file (the Std script relies on it): `EXPLAIN ANALYZE SELECT count(*) FROM hook.raw_views.<code> WHERE ___Raw_filename = '<one file>'` shows `Scanning Files: 1/<n>`.
