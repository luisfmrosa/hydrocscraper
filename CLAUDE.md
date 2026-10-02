# hydrocscraper — Claude context

## User

- **Name:** Luis Fernando Marques Rosa
- **Email:** falecomluisao@gmail.com

## Project overview

`hydrocscraper` is a modular pipeline that collects official hydrocarbon production data from multiple national and international sources. It follows the Hook methodology, with these layers:

- **Raw**: bucket `hydroc-raw`.
- **Lake, Library, DWH, Hook**: DuckLakes with their catalogs in Postgres and their data in `hydroc-<layer>` buckets.

It all runs on Incus. See `docs/architecture.md` and `docs/architecture_v2.md`.

## Running

```bash
python main.py --mode full                        # full load
python main.py --mode full --sources npd          # single source
python main.py --mode incremental                 # scheduled updates
python main.py --mode discover [--seed FILE]      # known-sources snapshot
pytest                                            # tests
```

## Key conventions

- Raw files are stored as received under `s3://hydroc-raw/{source}/{dataset}/year_month={YYYY-MM}/{stem}_{YYYYMMDD_HHmm}{ext}`.
- Watermarks are rows in `hook.metadata.watermark`, which is append-only; read them from `watermark_latest`.
- DuckLake objects are created by the DuckDB server at startup from `sql/ddl/`. Every script must be idempotent (`IF NOT EXISTS`). There is no app init mode.
- The app reaches DuckDB only through `storage/duck.py` (`CONNECT 'quack:...' (DISABLE_SSL true)`, then `execute()` with SQL literals; bound parameters aren't forwarded).
- DuckDB is 2.0.0-dev. The client wheel (`requirements.txt`) and the server CLI must be the exact same build: `duckdb_staged` (Incus Ansible) and `DUCKDB_STAGED` (`architecture/docker/duckdb/Dockerfile`). It needs an AVX2 CPU; the homelab Incus server has none.
- The scraper registry is in `config.py` and maps source IDs to scraper class paths.
- New scrapers go in `scrapers/` and inherit from `scrapers/base.py`.
- Infrastructure setups live side by side under `architecture/`: `incus/` (OpenTofu `tofu/` + Ansible `ansible/`) and `docker/` (Compose with RustFS). Both run the same `sql/ddl`. Never commit tfstate, `*.tfvars`, `vault.yml`, `local.yml` or `.env`.
