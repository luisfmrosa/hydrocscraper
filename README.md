# hydrocscraper

A modular pipeline that collects official hydrocarbon production data from national and international sources, stores raw downloads, and transforms them into a unified analytical dataset.

## Overview

```
Scrapers (per source) ── hydroc-app
      │  boto3
      ▼
Raw      s3://hydroc-raw/<source>/<dataset>/year_month=<YYYY-MM>/<file>_<YYYYMMDD_HHmm>
      │
      ▼  (DuckDB server hydroc-duckdb, quack protocol, DuckLake catalogs in Postgres)
Lake → Library (frame / latest) → DWH (supply)        Hook (metadata / raw_views)
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
docker compose run --rm app python main.py --mode discover --seed discovery/known_sources.json
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
.venv/bin/python main.py --mode discover --seed discovery/known_sources.json
.venv/bin/python main.py --mode full

# 4. Restart the server so the raw views get created over the new files
incus exec hydroc-duckdb --project hydroc -- systemctl restart duckdb-quack
```

Local development: `pip install -r requirements.txt`, then copy `.env.example` to `.env`. Tests: `pytest`.

## Usage

```bash
# Full download (all registered sources, or a subset)
python main.py --mode full
python main.py --mode full --sources npd

# Incremental update: stores a file only when new periods appear
python main.py --mode incremental

# Write a new known-sources snapshot to s3://hydroc-raw/metadata/known_sources/
python main.py --mode discover
python main.py --mode discover --seed discovery/known_sources.json   # one-time import

# Verbose / debug logging
python main.py --mode full -v
```

DuckLake schemas and tables are not created by the app. The DuckDB server applies `sql/ddl/` every time it starts.

## Adding a New Scraper

1. Create `scrapers/{source_id}.py`, inheriting from `scrapers.base.BaseScraper`.
2. Implement `full_load()`, `incremental_load()` and `parse()`. Use `fetch_to_temp()`, `store_raw(path, dataset)` and `save_watermark(dataset, ...)`.
3. Register the class in `config.py` under `SCRAPER_REGISTRY`.
4. Optionally add a view in `sql/ddl/raw_views/` and a `.read` line in `sql/ddl/init_server.sql`.
