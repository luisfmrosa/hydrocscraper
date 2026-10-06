---
name: add-dataset
description: End-to-end checklist for adding a new dataset to hydrocscraper — static metadata, scraper class (Python writes only to Raw), raw view, Std script (typing, flattening), std views, Lake tables and Lake load scripts, then tests and a Docker run. Use when the user asks to add, implement or onboard a new source or dataset.
---

# Add a dataset

Input: the source (e.g. `nsta`), the dataset name (e.g. `field_production_monthly`) and where the data comes from. The dataset code is `<source>_<dataset>`.

Before writing code, confirm with the user:
- the business keys;
- the source kind (see the table below);
- whether it's tabular. If it isn't (nested JSON…), agree on the **sub-tables**: one per independent structure, including the top level, each with its own keys.

## The pipeline

```
Python (scraper)          SQL on the DuckDB server
download ──► Raw ──► raw view ──► Std script ──► Std (Parquet) ──► std view ──► Lake
            hydroc-raw   hook.raw_views   sql/std/…    hydroc-std    hook.std_views   lake.<source>.*
```

Python **only writes to Raw**. Everything from Raw on is static SQL.

| Source kind | Python writes to Raw | Raw view reads |
|---|---|---|
| 1. File DuckDB reads (CSV, TSV, xlsx, JSON, Parquet…) | the file as received (`store_raw`) | those files |
| 2. Legacy format (`.xls`, HTML) | the file as received **and** a Parquet conversion with the same `ts` (`store_table`); the conversion is dataset-specific (e.g. which tab) and keeps values as received, as text | the `*.parquet` conversions |
| 3. Database table / SDK | the extract as Parquet (`store_table`) | `*.parquet` |

The watermark's `raw_file` is the file the raw view reads (the conversion in case 2).

| | Tabular | Non-tabular |
|---|---|---|
| `datasets.csv` rows | 1, with keys, empty `parent_code` | 1 for the dataset (empty keys: no table) + 1 per sub-table: code `<source>_<dataset>_<sub_table>`, its keys (`parent` first except the top level), `parent_code` = the dataset (top level) or the parent sub-table |
| Raw view, Std script | 1 each | 1 each (the Std script writes every sub-table) |
| Std view, Lake table, Lake loads | 1 set, code `<source>_<dataset>` | 1 set per sub-table |
| Watermark | `(source, dataset)` | `(source, dataset)` only |

## Checklist

1. **Static metadata** (`data/static/`):
   - `sources.csv`: add the source if it's new (next `id`, `code`, `name`, `scope` Public/Private, `url`).
   - `datasets.csv`: the rows above. Columns: next `id`; `code`; `name`; `source_id`; `copyright`; `type` (`FILE`/`API`/`TABLE`); `format` (of the source); `parent_code`; `granularity`; `periodicity`; `keys` (comma-separated, quoted); `url`.
   - `business_concepts.csv` / `hooks.csv` (`id`, `code`, `name`, `description`): only if the dataset introduces new ones; ask the user.
2. **Scraper** (Python collects only):
   - `scrapers/<source>/<dataset>.py`, with `scrapers/<source>/__init__.py` if the source is new. Follow `scrapers/npd/field_production_monthly.py`: set `source`/`dataset`, implement `download_full()` and `download_incremental()` (returns `True` when a file was stored), use `fetch_to_temp()`, `store_raw()` / `store_table()`, and end with `save_watermark(..., status="raw", raw_file=<key the raw view reads>)`.
   - **Snapshot sources** (every download is the whole dataset, like NPD): in `download_incremental()`, store the file only `if self.is_new_content(path)` (MD5 against the watermark's file), so revisions of past periods are caught. First check that two downloads of unchanged data are byte-identical; if the export embeds a generation time, ask the user.
   - Case 2: capture one `ts = storage.raw.utc_now()` and pass it to both `store_raw(path, ts=ts)` and `store_table(table, name, ts=ts)`. Keep the conversion in a pure function so it can be unit-tested.
   - Register it in `config.SCRAPER_REGISTRY` under the dataset code, with its `source` and dotted `class` path. Sub-tables are not registered: the base class finds them in `datasets.csv` through `parent_code`.
3. **Raw view:** follow the `raw-view` skill.
4. **Std script:** follow the `std-script` skill (typing; flattening if non-tabular; checks).
5. **Std view(s):** follow the `std-view` skill, once per row with keys.
6. **Lake table(s):** follow the `lake-table` skill, once per row with keys.
7. **Lake loads:** follow the `lake-load-script` skill, once per row with keys.
8. **Server registration:** `.read` lines for the raw view, each std view and each Lake table in `sql/ddl/init_server.sql`.
9. **Tests:** a unit test for the scraper's pure helpers (like `tests/test_npd.py`) and a SQL test running the real raw view, Std script, std view and Lake scripts on a local DuckDB (like `tests/test_lake.py`). Then run `pytest` (in the app container: `docker compose run --rm --no-deps app sh -c "pip install -q pytest && python -m pytest -q"`).
10. **Docker stack** (`architecture/docker`):
    1. `docker compose restart duckdb`, then check the logs;
    2. `docker compose run --rm app python main.py --mode full --datasets <code>`;
    3. `docker compose run --rm app python main.py --mode incremental --datasets <code>`;
    4. `--mode full` again: the log must show `1 of n Raw files converted` (only the new file);
    5. the checks listed in each skill; the latest watermark rows must read `lake`, `std`, `raw`.
11. **Docs:** add the dataset to `README.md` (data sources table) and to `docs/data_sources.md` if needed.

## Done when

- `pytest` passes;
- the server starts without errors other than "No files found";
- full and incremental succeed on Docker, for every Lake table of the dataset;
- every Raw file has its Std file(s), with the same `year_month` and timestamp;
- the Lake's MD5s match the std views; no orphan `parent` values.
