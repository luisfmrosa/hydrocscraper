---
name: std-script
description: Write the static SQL script that converts one Raw file of a dataset into typed Parquet in the Std bucket (hydroc-std) — casting, flattening non-tabular data into sub-tables, data-quality checks. Use when adding a dataset to hydrocscraper, after its raw view exists, or when its typing or flattening changes.
---

# Std script for a dataset

Input: the dataset code `<source>_<dataset>`, its raw view (`raw-view` skill), and its Std tables from `data/static/datasets.csv` (the rows reached through `parent_code`, with their `keys`).

Every dataset has exactly one Std script. It is dataset-specific: write the logic for this source's structure.

**Worked example (tested, tabular):** `sql/std/npd/field_production_monthly.sql`.

## Contract

- **File:** `sql/std/<source>/<dataset>.sql`. Run by `storage/std.py` after each download (the watermark's file) and for every Raw file in a full load.
- **Input:** one Raw file, given by the runner as the variable `raw_file` (full `s3://hydroc-raw/…` path). Read it **through the raw view**, filtered with `WHERE ___Raw_filename = getvariable('raw_file')` (DuckDB then reads only that file). Never read anything else.
- **Output:** one `COPY … TO … (FORMAT parquet)` per Std table, to
  `s3://hydroc-std/<source>/<table>/year_month=<ym>/<source>_<table>_<ts>.parquet`,
  where `<table>` is `<dataset>` (tabular) or `<dataset>_<sub_table>`, and `<ym>`/`<ts>` come from `raw_file`. The shared timestamp links Std to Raw and to the watermark; never use the conversion time.
- **Columns:** keys first, in the order of `keys`, then the others; final names and types (`col::TYPE AS col`). Use the narrowest correct type: `INTEGER` for years and months, `BIGINT` for ids, `DOUBLE` for measures, `DATE`/`TIMESTAMP` (parse with `strptime` if needed), `VARCHAR` otherwise. These names, order and types are the std view's and the Lake table's.
- **Fail loudly:** use `::TYPE`, not `TRY_CAST`. A value that doesn't cast fails the step, the watermark stays at `raw` and the next run retries. Data-quality expectations (schema changes, value checks) go here too, as statements that raise an `error(...)`.
- **Idempotent:** rerunning it overwrites the same files with the same content.

`COPY … TO` takes a constant expression in parentheses, including `getvariable()`, but no subquery: build each path with `SET VARIABLE` first.

## Tabular template

```sql
-- Std: <source> <dataset> (tabular).
-- Converts one Raw file (variable raw_file) to typed Parquet in Std, with the
-- Raw file's year_month and timestamp. Keys: <keys>.
SET VARIABLE std_file =
    's3://hydroc-std/<source>/<dataset>/year_month='
    || regexp_extract(getvariable('raw_file'), 'year_month=([^/]+)/', 1)
    || '/<source>_<dataset>_'
    || regexp_extract(getvariable('raw_file'), '_(\d{8}_\d{4})\.[^./]+$', 1)
    || '.parquet';

COPY (
    SELECT <key>::TYPE AS <key>, …, <col>::TYPE AS <col>, …
    FROM hook.raw_views.<source>_<dataset>
    WHERE ___Raw_filename = getvariable('raw_file')
) TO (getvariable('std_file')) (FORMAT parquet);
```

## Non-tabular: flattening

Flatten **only** non-tabular data (e.g. nested JSON). One Std table per independent structure, including the top level, each with its own `datasets.csv` row (`code` = `<source>_<dataset>_<sub_table>`, `parent_code`, `keys`).

- Every sub-table except the top level starts with `parent` (`VARCHAR`): the parent row's key values cast to text and joined with `chr(31)`: `concat_ws(chr(31), p.k1::VARCHAR, p.k2::VARCHAR) AS parent`. Its key is `parent` plus its own key columns.
- One `SET VARIABLE` path and one `COPY` per sub-table. `unnest(list)` of an empty list yields no rows, which is right for children.
- A sub-table with no rows in a file still gets its (empty) file. Note: the incremental Lake load can't detect deletions from an empty file (`lake-load-script` skill); raise it with the user if a sub-table can legitimately become empty.

```sql
SET VARIABLE ym = regexp_extract(getvariable('raw_file'), 'year_month=([^/]+)/', 1);
SET VARIABLE ts = regexp_extract(getvariable('raw_file'), '_(\d{8}_\d{4})\.[^./]+$', 1);

COPY (
    SELECT r.<key>::TYPE AS <key>, r.<col>::TYPE AS <col>
    FROM hook.raw_views.<source>_<dataset> r
    WHERE r.___Raw_filename = getvariable('raw_file')
) TO ('s3://hydroc-std/<source>/<dataset>_<top>/year_month=' || getvariable('ym')
      || '/<source>_<dataset>_<top>_' || getvariable('ts') || '.parquet') (FORMAT parquet);

COPY (
    SELECT concat_ws(chr(31), r.<key>::VARCHAR) AS parent, c.<key>::TYPE AS <key>, c.<col>::TYPE AS <col>
    FROM hook.raw_views.<source>_<dataset> r, unnest(r.<children>) AS u(c)
    WHERE r.___Raw_filename = getvariable('raw_file')
) TO ('s3://hydroc-std/<source>/<dataset>_<child>/year_month=' || getvariable('ym')
      || '/<source>_<dataset>_<child>_' || getvariable('ts') || '.parquet') (FORMAT parquet);
```

## Verify

1. **Tests:** like `tests/test_lake.py`: write fixture Raw files to a temp folder, replace `s3://hydroc-raw/` and `s3://hydroc-std/` with local folders (create the Std folders first: a local `COPY` doesn't create them), `SET VARIABLE raw_file`, run the script, then check each Parquet file's path, types, row count and, if flattened, `parent` values.
2. **Docker stack:** `docker compose run --rm app python main.py --mode full --datasets <code>`. The log shows the Std script once per Raw file. Then list `s3://hydroc-std/<source>/`: one file per Std table per Raw file, with the Raw timestamps.
