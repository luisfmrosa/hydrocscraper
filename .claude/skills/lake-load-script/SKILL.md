---
name: lake-load-script
description: Write the static SQL scripts that load a Lake table from its std view — incremental (the Std file of the latest watermark vs current state) and full (set-based replay of every Std file) — appending new, changed and deleted rows. Use when adding a dataset or flattened table to hydrocscraper, after its std view and Lake table exist.
---

# Lake load scripts for a Std table

Input: a row of `data/static/datasets.csv` with keys, its `code` and `keys`. Its std view and Lake table must exist (`std-view` and `lake-table` skills).

Naming: `<table>` is the code without `<source>_` (`<dataset>` or `<dataset>_<sub_table>`); `<dataset>` is always the **downloaded** dataset, which owns the watermark.

**Worked examples (tested):**
- `sql/lake/no_sodir/field_production_monthly_incremental.sql`
- `sql/lake/no_sodir/field_production_monthly_full.sql`

Copy them and replace only: the table and view names, the key columns, the data column lists, the watermark filter (`'<source>'` / `'<dataset>'`), the Std file path built from the watermark, and the `'<code>'` datasource literal. Keep the logic unchanged.

## Files

- `sql/lake/<source>/<table>_incremental.sql`
- `sql/lake/<source>/<table>_full.sql`

The runner (`storage/lake.py`) finds them by these names. It runs the std view and Lake table scripts first, then the load. The load's last statement must be the `INSERT`: its row count is what gets logged. Lake loads read only `hook.std_views.*`, never raw views or Raw files.

## Rules both scripts implement

The **current state** of a key is its latest Lake row, by `___Lake_load_timestamp`. A load appends:

| Row | Condition | Values | `___Lake_isdeleted` |
|---|---|---|---|
| New | Key not in the Lake, or its latest row is a deletion | From the file | `false` |
| Changed | `___Std_md5` differs from the current `___Lake_md5` | From the file | `false` |
| Deleted | Current key (not already deleted) missing from the file | The current row's last known values | `true` |

In every row:
- `___Lake_load_timestamp` = the file's `___Std_file_timestamp`;
- `___Lake_sourcefile` = `___Std_filename`;
- `___Lake_datasource` = `'<code>'`;
- `___Lake_md5` = `___Std_md5`, or for deletions, the current row's MD5.

For a flattened table the key includes `parent`, so a child whose parent changed key shows up as a deletion plus a new row. That is expected.

## Incremental

- **Incoming rows:** the std view joined to `hook.metadata.watermark_latest` on `w.source = '<source>' AND w.dataset = '<dataset>'` and on the Std file derived from the watermark's Raw file (same `year_month` and timestamp):
  ```sql
  AND r.___Std_filename = 's3://hydroc-std/<source>/<table>/year_month='
      || regexp_extract(w.raw_file, 'year_month=([^/]+)/', 1)
      || '/<source>_<table>_'
      || regexp_extract(w.raw_file, '_(\d{8}_\d{4})\.[^./]+$', 1)
      || '.parquet'
  ```
  Then filter out files older than `max(___Lake_load_timestamp)` (coalesced to `'-infinity'`).
- **Current state:** `QUALIFY row_number() OVER (PARTITION BY <keys> ORDER BY ___Lake_load_timestamp DESC) = 1`.
- **Deletions:** take the file name and timestamp from a one-row `batch` CTE (`SELECT DISTINCT` over the incoming rows) with `CROSS JOIN`. If the file was filtered out, `batch` is empty and nothing gets deleted.
- **Empty file:** if a Std file has no rows (e.g. a sub-table empty in that download), `batch` is empty too and current keys are *not* deleted, while the full load (which numbers files by name) would delete them. Raise it with the user if a table can legitimately become empty.
- **Rerunning the same file** must add 0 rows.

## Full

- `TRUNCATE lake.<source>.<table>;` then one `INSERT … WITH … SELECT`. **No loops**, and no Python.
- `files`: the distinct `(___Std_filename, ___Std_file_timestamp)`, with `row_number() OVER (ORDER BY ___Std_file_timestamp, ___Std_filename) AS file_seq`.
- `observations`: std rows joined to `files`, with `lag(___Std_md5)`, `lag(file_seq)` and `lead(file_seq)` over `PARTITION BY <keys> ORDER BY file_seq`.
- **New, reappearing or changed:** `prev_seq IS NULL OR prev_seq < file_seq - 1 OR prev_md5 <> ___Std_md5`.
- **Deleted:** join to the next file `nf.file_seq = o.file_seq + 1`, where `next_seq IS NULL OR next_seq > file_seq + 1`. The row gets the next file's name and timestamp.

## Key matching

Join keys with `=` (keys are never NULL; the std view skill checks this). Always list every key column in `PARTITION BY` and in the joins, `parent` included.

## Verify

1. **Tests:** `tests/test_lake.py` runs the Sodir raw view, Std script, std view and Lake scripts on a local DuckDB with synthetic snapshots. Add an equivalent test for the new table (copy the fixtures, adapt the columns), or at least check these properties:
   - full = 0 deletions on the first file;
   - incremental file by file gives **the same rows** as full;
   - rerunning incremental adds 0.
2. **Docker stack:**
   - `docker compose run --rm app python main.py --mode full --datasets <dataset code>`, then `--mode incremental` (adds nothing when there's no new data). Both load every Lake table of the dataset.
   - Rerun the incremental load alone: `python -c "from storage import lake; print(lake.load('<source>', '<table>', 'incremental'))"` must print 0, and the incoming join must match the latest Std file (count the rows of the `incoming` CTE: it must equal the file's row count, not 0).
   - Then check that the MD5s match the std view:
     ```sql
     SELECT count(*) FROM lake.<source>.<table> l
     JOIN hook.std_views.<code> r ON r.___Std_filename = l.___Lake_sourcefile AND <keys match> AND r.___Std_md5 = l.___Lake_md5
     WHERE NOT l.___Lake_isdeleted
     ```
     This must equal the number of non-deleted Lake rows.
