# hydrocscraper

A modular pipeline that collects official hydrocarbon production data from national and international sources, stores raw downloads, and transforms them into a unified analytical dataset.

## Overview

```
Scrapers (per source) ── hydroc-app
      │  boto3
      ▼
Raw      s3://hydroc-raw/<source>/<dataset>/year_month=<YYYY-MM>/<file>_<YYYYMMDD_HHmm>
      │
      ▼  static SQL on the DuckDB server hydroc-duckdb (quack protocol)
Std      s3://hydroc-std/<source>/<table>/year_month=<YYYY-MM>/<source>_<table>_<YYYYMMDD_HHmm>.parquet
      │
      ▼  (DuckLake catalogs in Postgres)
Lake → Library (frame / latest views, with hooks) → DWH (supply)        Hook (metadata / raw_views / std_views)
```

The stack runs on Incus: three containers (Postgres, a DuckDB quack server and the app) and one S3 bucket per layer. See [docs/architecture.md](docs/architecture.md).

## Data Sources

### International organizations

| Source | Granularity | Format | Notes |
|--------|-------------|--------|-------|
| JODI Oil | Country | CSV | ~100 countries, ~2-month lag |
| JODI Gas | Country | CSV | Same model as JODI Oil |
| EIA International | Country | JSON API | Free API key required |
| IEA Monthly Oil Statistics | Country | XLSX | Free for OECD; subscription for non-OECD |
| OPEC MOMR | Country | XLSX/PDF | OPEC members only |
| OPEC Annual Statistical Bulletin | Country | XLSX | Historical series |
| Energy Institute Statistical Review | Country | XLSX | Formerly BP Statistical Review |

### National agencies — field / well level

| Country | Agency | Granularity | Data Quality |
|---------|--------|-------------|--------------|
| Norway | Sokkeldirektoratet (NPD) | Field / Well | Excellent |
| United Kingdom | NSTA | Field | Excellent |
| Brazil | ANP | Field / Well | Good |
| Canada | CER | Province | Good |
| Netherlands | NLOG | Field | Good |
| Mexico | CNH | Field | Fair |
| Colombia | ANH | Field | Fair |
| Argentina | Secretaría de Energía | Field / Well | Fair |

## Deployment

The stack can run in two setups, each in its own folder under `architecture/`. Both use the same code and the same `sql/ddl` scripts. DuckDB 2.0.0-dev needs a CPU with AVX2 in either setup.

### Docker (local / test)

Runs RustFS (S3), Postgres, the DuckDB quack server and the app with Docker Compose. Full instructions: [architecture/docker/README.md](architecture/docker/README.md).

```bash
cd architecture/docker
cp .env.example .env                                   # set every value
docker compose up -d --build
docker compose run --rm app python main.py --mode full
```

### Incus

Prerequisites:
- The Incus client, with a remote configured for your Incus server.
- OpenTofu.
- Ansible, run from WSL or Linux, with the collections from `architecture/incus/ansible/requirements.yml`.

```bash
# 1. Infrastructure: bridge, project, buckets and keys, containers
cd architecture/incus/tofu
cp terraform.tfvars.example terraform.tfvars        # adjust
tofu init && tofu apply

# 2. Configuration: Postgres catalogs, DuckDB quack server, app
cd ../ansible
ansible-galaxy collection install -r requirements.yml
cp group_vars/all/vault.yml.example group_vars/all/vault.yml   # fill in
cp group_vars/all/local.yml.example group_vars/all/local.yml   # Incus remote/host, repo URL
ansible-playbook -i inventory.yml site.yml   # -i: under WSL /mnt/c, ansible.cfg is ignored

# 3. First loads, from hydroc-app (/opt/hydrocscraper)
.venv/bin/python main.py --mode full

```

Local development: `pip install -r requirements.txt`, then copy `.env.example` to `.env`. Tests: `pytest`.

## Usage

```bash
# Full: download the complete dataset into Raw, convert Raw files that have no Std file yet, then rebuild the Lake
# (replaying every Std file, so the history of changes between downloads is kept)
python main.py --mode full                                       # every dataset
python main.py --mode full --sources npd                         # every dataset of a source
python main.py --mode full --datasets npd_field_production_monthly

# Incremental: store a file only when new data appears, convert it to Std, then load its changes into the Lake
# (first finishes a file left half-way by a failed run)
python main.py --mode incremental

# After changing a Std script (or to recover from a schema change): convert every Raw file again
python main.py --mode full --rebuild-std --datasets npd_field_production_monthly

# Verbose / debug logging
python main.py --mode full -v
```

The DuckDB server creates the layer schemas and the Hook metadata tables at every start (`sql/ddl/`). The app (re)creates a dataset's raw view, std views and Lake tables before each step, so a first load needs no server restart.

## Adding a New Dataset

One scraper class per source and dataset:

1. Create `scrapers/<source>/<dataset>.py` with a class inheriting from `scrapers.base.BaseScraper`. Set `source` and `dataset`, then implement `download_full()` and `download_incremental()` (return `True` when a file was stored). Use `fetch_to_temp()`, `store_raw(path)` (or `store_table(...)` for a Parquet conversion or an API/database extract) and `save_watermark(..., status="raw")`. Python only writes to Raw; the base class then runs Std and the Lake loads.
2. Register the class in `config.py` under `SCRAPER_REGISTRY`, keyed by its code `<source>_<dataset>`.
3. Add the dataset to `data/static/datasets.csv` (one row per Std/Lake table with its `keys`; flattened tables linked by `parent_code`), and the source to `data/static/sources.csv` if it's new.
4. Write its static SQL (the project skills `raw-view`, `std-script`, `std-view`, `lake-table` and `lake-load-script` in `.claude/skills/` describe each step; `add-dataset` runs the whole checklist):
   - raw view `sql/ddl/raw_views/<nnn>_<source>_<dataset>.sql`;
   - Std script `sql/std/<source>/<dataset>.sql`;
   - per Std table: std view `sql/ddl/std_views/<nnn>_<code>.sql`, Lake table `sql/ddl/lake/<code>.sql`, Lake loads `sql/lake/<source>/<table>_full.sql` and `_incremental.sql`;
   - `.read` lines for the views and Lake tables in `sql/ddl/init_server.sql`.
5. Restart the DuckDB server so it reloads the static metadata.
