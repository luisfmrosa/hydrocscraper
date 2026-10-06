# hydrocscraper — Claude context

## User

- **Name:** Luis Fernando Marques Rosa
- **Email:** falecomluisao@gmail.com

## Project overview

`hydrocscraper` is a modular pipeline that collects official hydrocarbon production data from multiple national and international sources. It follows the Hook methodology, with these layers:

- **Raw**: bucket `hydroc-raw`, files as received.
- **Std**: bucket `hydroc-std`, every Raw file as typed (and, if nested, flattened) Parquet. Derived from Raw and rebuildable; the Lake loads from it.
- **Lake, Library, DWH, Hook**: DuckLakes with their catalogs in Postgres and their data in `hydroc-<layer>` buckets.

It all runs on Incus. See `docs/architecture.md`.

## Running

```bash
python main.py --mode full                        # full load
python main.py --mode full --sources npd          # every dataset of a source
python main.py --mode incremental --datasets npd_field_production_monthly
python main.py --mode full --rebuild-std             # after changing a Std script
pytest                                            # tests
```

## Key conventions

- Raw files are stored as received under `s3://hydroc-raw/{source}/{dataset}/year_month={YYYY-MM}/{stem}_{YYYYMMDD_HHmm}{ext}`. Std files: `s3://hydroc-std/{source}/{table}/year_month={YYYY-MM}/{source}_{table}_{YYYYMMDD_HHmm}.parquet`, with the Raw file's period and timestamp (`{table}` = the dataset, or `{dataset}_{sub_table}` when flattened).
- Watermarks are rows in `hook.metadata.watermark`, which is append-only; read them from `watermark_latest`. `status` is the step reached by the file: `raw` → `std` → `lake` (old rows: `ok`); an incremental run first finishes a pending file.
- DuckLake objects are created by the DuckDB server at startup from `sql/ddl/`. Every script must be idempotent (`IF NOT EXISTS`). There is no app init mode.
- The app reaches DuckDB only through `storage/duck.py` (`CONNECT 'quack:...' (DISABLE_SSL true)`, then `execute()` with SQL literals; bound parameters aren't forwarded).
- DuckDB is 2.0.0-dev. The client wheel (`requirements.txt`) and the server CLI must be the exact same build: `duckdb_staged` (Incus Ansible) and `DUCKDB_STAGED` (`architecture/docker/duckdb/Dockerfile`). It needs an AVX2 CPU; the homelab Incus server has none.
- One scraper class per source and dataset: `scrapers/<source>/<dataset>.py`, inheriting from `scrapers/base.py` (implement `download_full` / `download_incremental`; the base class then runs Std and the Lake loads). Register it in `config.SCRAPER_REGISTRY` under its code `<source>_<dataset>`, add its rows to `data/static/datasets.csv` (one per Std/Lake table, with `keys`; flattened tables linked by `parent_code`) and its SQL files (see below).
- Python only collects data (download → Raw → watermark) and always writes to Raw, never to Std: files DuckDB reads as received; legacy formats (.xls, HTML) as received plus a Parquet conversion with the same timestamp (`store_table`); database/SDK extracts as Parquet. Everything from Raw on is static SQL run on the server: per dataset a raw view `sql/ddl/raw_views/<nnn>_<code>.sql` (as received, `___Raw_filename/_year_month/_file_timestamp`) and a Std script `sql/std/<source>/<dataset>.sql` (one Raw file, given as variable `raw_file` → typed/flattened Parquet via `COPY … TO`; it checks the file's columns first, since `union_by_name` would turn a renamed column into NULLs; data-quality checks go here); per Std table a std view `sql/ddl/std_views/<nnn>_<code>.sql` (+ `___Std_md5/_filename/_year_month/_file_timestamp`), a Lake table `sql/ddl/lake/<code>.sql` (+ the five `___Lake_*` columns) and load scripts `sql/lake/<source>/<table>_{full,incremental}.sql`. `storage/std.py` and `storage/lake.py` only run them. The project skills in `.claude/skills/` describe how to write each one.
- Lake: `lake.<source>.<table>`, append-only (new, changed and deleted rows), loaded from the std view. Full = Std for every Raw file that has none (every file with `--rebuild-std`), then truncate + one set-based replay of every Std file oldest first (this keeps the history of changes between snapshots); incremental = the Std file of the latest watermark. Both must give the same result.
- Static Hook metadata lives in `data/static/*.csv` (the only versioned part of `data/`) and is rebuilt into `hook.metadata.*` at each server start.
- Infrastructure setups live side by side under `architecture/`: `incus/` (OpenTofu `tofu/` + Ansible `ansible/`) and `docker/` (Compose with RustFS). Both run the same `sql/ddl`. Never commit tfstate, `*.tfvars`, `vault.yml`, `local.yml` or `.env`.
