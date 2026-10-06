# Architecture

## Overview

hydrocscraper collects official hydrocarbon production data from multiple sources and organises it in layers following the Hook methodology. The stack is cloud-ready: object storage uses the S3 API, catalogs live in Postgres, and DuckDB runs as a server in a container. The design rationale is in [architecture_v2.md](architecture_v2.md).

The same stack can be deployed two ways (see *Infrastructure* below): on an Incus server (`architecture/incus/`) or with Docker Compose (`architecture/docker/`). The diagram shows the Incus layout; in Docker the containers are `app`, `duckdb`, `postgres` and `rustfs`.

```
                         Incus project "hydroc"  (bridge hydroc-br0, 10.10.40.0/24)

  ┌───────────────┐   boto3 (raw files)     ┌──────────────────────────────────────┐
  │  hydroc-app   │────────────────────────▶│ Incus S3 buckets (<incus-host>:8555) │
  │  main.py      │                         │ hydroc-raw  hydroc-std  hydroc-lake  │
  │  10.10.40.30  │                         │ hydroc-library  hydroc-dwh           │
  └──────┬────────┘                         │ hydroc-hook                          │
         │ CONNECT quack (:9494)            └──────────────────▲───────────────────┘
         ▼                                                     │ S3 secrets
  ┌──────────────────────────────┐   DuckLake catalogs   ┌─────┴────────────────┐
  │ hydroc-duckdb  10.10.40.20   │──────────────────────▶│ hydroc-pg            │
  │ duckdb -init init_server.sql │   cat_hydroc_<layer>  │ 10.10.40.10          │
  │ lake · library · dwh · hook  │                       │ PostgreSQL           │
  └──────────────────────────────┘                       └──────────────────────┘
```

| Component | Role |
|-----------|------|
| `hydroc-app` | Runs the scrapers (`main.py`). It uploads raw files to `hydroc-raw` and runs the Std and Lake SQL and the metadata reads and writes through the quack server. It holds no catalog credentials and needs no access to `hydroc-std`. |
| `hydroc-duckdb` | DuckDB CLI server. It attaches the four DuckLakes, applies the DDL in `sql/ddl/` at startup and serves the quack protocol. |
| `hydroc-pg` | PostgreSQL. It holds one DuckLake catalog database per layer: `cat_hydroc_<layer>`, owned by `user_hydroc_<layer>`. |
| S3 buckets | One bucket per layer, `hydroc-<layer>`. Incus storage buckets (one key per bucket) or RustFS in Docker (one root key). |

---

## Layers

| Layer | Storage | Contents |
|-------|---------|----------|
| **Raw** | `hydroc-raw` (plain bucket) | Files exactly as received, plus `metadata/` (copies of the static Hook metadata) |
| **Std** | `hydroc-std` (plain bucket) | Every Raw file as typed Parquet, flattened when not tabular. Derived from Raw; the Lake loads from it |
| **Lake** | DuckLake `lake`, one schema per source | Append-only change records per Std table, e.g. `lake.npd.field_production_monthly` (see *Lake loading*) |
| **Library** | DuckLake `library`, schemas `frame` and `latest` | SCD2-like Frame objects and latest-version views. *Planned.* |
| **DWH** | DuckLake `dwh`, schema `supply` | Business views and models |
| **Hook** | DuckLake `hook`, schemas `metadata`, `raw_views` and `std_views` | `metadata`: `sources`, `datasets`, `business_concepts`, `hooks` (static, from `data/static/`) and `watermark`. `raw_views`: one view per dataset over its Raw files. `std_views`: one view per Std table over its Parquet files |

### Raw bucket layout

```
hydroc-raw/
├── <source>/<dataset>/year_month=<YYYY-MM>/<stem>_<YYYYMMDD_HHmm><ext>
│     e.g. npd/field_production_monthly/year_month=2026-09/field_production_monthly_20260929_1000.csv
└── metadata/
    └── <name>/<name>.csv        sources, datasets, business_concepts, hooks
```

- `year_month` defaults to the UTC month of the download. A scraper may pass the reference period instead, for sources that publish one file per period.
- Every download gets its own timestamped file, so nothing is overwritten.

### Std bucket layout

```
hydroc-std/
└── <source>/<table>/year_month=<YYYY-MM>/<source>_<table>_<YYYYMMDD_HHmm>.parquet
      e.g. npd/field_production_monthly/year_month=2026-09/npd_field_production_monthly_20260929_1000.parquet
```

- `<table>` is the dataset, or `<dataset>_<sub_table>` for a flattened table of a non-tabular dataset.
- One file per Std table per Raw file, with the Raw file's `year_month` and timestamp. Std is derived from Raw and can always be rebuilt from it; a full load does so.

### Watermarks

`hook.metadata.watermark` is append-only and gets one row per completed step of a load:

| Column | Description |
|--------|-------------|
| `source`, `dataset` | For example `npd`, `field_production_monthly` |
| `load_mode` | `full` or `incremental` |
| `last_period_fetched` | `YYYY-MM` |
| `status` | Step reached by `raw_file`: `raw` (stored), `std` (converted), `lake` (loaded). Rows from before the Std layer have `ok` (done). |
| `raw_file` | Object key in `hydroc-raw` of the file the Std script reads |
| `updated_at` | UTC timestamp |

`hook.metadata.watermark_latest` returns the most recent row per `(source, dataset)`. An incremental run first finishes a file whose latest status is `raw` or `std`, so a failed step is retried.

### Static Hook metadata

`data/static/{sources,datasets,business_concepts,hooks}.csv` are versioned in the repository; they are the only versioned content of `data/`. At every server start, `sql/ddl/45_hook_static.sql` copies each one to `s3://hydroc-raw/metadata/<name>/<name>.csv` and rebuilds `hook.metadata.<name>` from that copy (`CREATE OR REPLACE`), so the tables always follow the repository. Edit a CSV, then restart the server (Docker: `docker compose restart duckdb`; Incus: re-run Ansible).

`datasets` has one row per Std/Lake table: `code` (`<source>_<dataset>`, or `<source>_<dataset>_<sub_table>` for a flattened table), `source_id` (→ `sources.id`), `type` (`FILE`, `API`, `TABLE`), `parent_code` and `keys` (the business key columns, comma-separated). A non-tabular dataset also has a row of its own with empty `keys` (no table); its flattened tables point to it, or to their parent table, through `parent_code`. The app (`storage/datasets.py`) follows `parent_code` to find the tables a download feeds. The keys are written into each table's SQL scripts.

### Transformations: static SQL

Python only collects data and only writes to Raw:

1. a file DuckDB can read (CSV, TSV, xlsx, JSON, Parquet…): as received;
2. a legacy format DuckDB can't read (`.xls`, HTML): as received, plus a Parquet conversion with the same timestamp (`BaseScraper.store_table`, values kept as received);
3. a database table or an API read with an SDK: the extract as Parquet (`store_table`).

Everything after that is static SQL run on the DuckDB server:

| File | Content |
|------|---------|
| `sql/ddl/raw_views/<nnn>_<source>_<dataset>.sql` | Raw view `hook.raw_views.<source>_<dataset>`: the Raw files as received (`CREATE OR REPLACE`) |
| `sql/std/<source>/<dataset>.sql` | Std script: one Raw file (variable `raw_file`) → typed, flattened if needed, Parquet in `hydroc-std` (`COPY … TO`). Data-quality checks go here. |
| `sql/ddl/std_views/<nnn>_<code>.sql` | Std view `hook.std_views.<code>` per Std table (`CREATE OR REPLACE`) |
| `sql/ddl/lake/<code>.sql` | Lake schema and table `lake.<source>.<table>` (`IF NOT EXISTS`) |
| `sql/lake/<source>/<table>_full.sql` | Full load |
| `sql/lake/<source>/<table>_incremental.sql` | Incremental load |

The server runs the view and Lake table scripts at startup. The app's runners (`storage/std.py`, `storage/lake.py`, no logic) re-run the raw view before the Std script and the std view and Lake table before each load, so a new dataset or a first download needs no server restart.

### Raw view columns

The source's columns as received (CSV-like files read with `all_varchar`, original names), followed by:

| Column | Content |
|--------|---------|
| `___Raw_filename` | Full S3 path of the file |
| `___Raw_year_month` | `year_month` partition of the file |
| `___Raw_file_timestamp` | Download time (UTC), from the file name suffix `_YYYYMMDD_HHmm` |

### Std view columns

The Std table's typed columns (keys first; the same order and types as the Lake table), followed by:

| Column | Content |
|--------|---------|
| `___Std_md5` | MD5 of the non-key columns: `md5(concat_ws(chr(31), coalesce(col::VARCHAR, '') …))`, in the view's column order |
| `___Std_filename` | Full S3 path of the Std file |
| `___Std_year_month` | `year_month` partition (the Raw file's) |
| `___Std_file_timestamp` | Download time (UTC) of the Raw file, from the file name suffix |

### Lake tables

One schema per source, one append-only table per Std table. The data columns are the std view's, followed by:

| Column | Content |
|--------|---------|
| `___Lake_md5` | The std view's `___Std_md5` |
| `___Lake_load_timestamp` | When the change was **observed**: the file's download time (`___Std_file_timestamp`), not the insert time. Replayed history therefore keeps its real dates. |
| `___Lake_datasource` | Table code (`hook.metadata.datasets.code`) |
| `___Lake_sourcefile` | S3 path of the Std file the change was detected in |
| `___Lake_isdeleted` | `true`: the key disappeared from that file; the row repeats its last known values |

**Loads.** The current state of a key is its latest Lake row (by `___Lake_load_timestamp`). Each script appends:
- new rows: an unknown key, or a key whose latest row is a deletion;
- changed rows: a different MD5;
- deletion rows: current keys missing from the file.

- **Incremental** (`--mode incremental`, only when a new file was stored): compares the Std file of the latest watermark with the current state. A file older than the Lake's latest load is ignored, and running the same file again adds nothing.
- **Full** (`--mode full`, after the download and the Std rebuild): `TRUNCATE`, then one set-based statement replays every Std file from oldest to newest. Files are numbered by download time; per key, `LAG` finds new, reappearing and changed rows, and `LEAD` finds the file in which a key disappears. The result equals running the incremental load once per file; the tests check this.

---

## DuckDB server

`sql/ddl/init_server.sql` is the server's entry point, and it runs at every start of `duckdb-quack.service`:

```
.bail off                        -- keep going if a raw/std view has no files yet
00_extensions.sql                -- httpfs, postgres, ducklake, quack
/opt/duckdb/secrets.sql          -- rendered by Ansible: S3 + DuckLake secrets, quack token
10_attach.sql                    -- ATTACH 'ducklake:ducklake_<layer>' AS <layer>
20_library.sql … 41_*.sql        -- schemas, watermark table/view (IF NOT EXISTS)
lake/*.sql                       -- Lake tables (IF NOT EXISTS)
raw_views/*.sql                  -- hook.raw_views.* over s3://hydroc-raw/...
std_views/*.sql                  -- hook.std_views.* over s3://hydroc-std/...
99_serve.sql                     -- quack_serve('quack:0.0.0.0:9494', token = …)
```

To add an object, add an idempotent script and a `.read` line to `init_server.sql`, then re-run Ansible (Incus) or `docker compose restart duckdb` (Docker), which restarts the server.

The app talks to the server through `storage/duck.py`. It runs `CONNECT 'quack:<host>:9494' (DISABLE_SSL true)`, after which every statement executes on the server and can use fully qualified names such as `hook.metadata.watermark`. Behaviour of quack in DuckDB 2.0.0-dev to keep in mind:

- **Same build on both sides.** Different 2.0 dev builds can't talk to each other; the server answers with HTTP 500. `duckdb==` in `requirements.txt` and the server's staged build must match: `duckdb_staged` in Ansible (Incus) and `DUCKDB_STAGED` in `architecture/docker/duckdb/Dockerfile`. Both install the CLI with the official script (`https://install.duckdb.org`) pinned via `DUCKDB_STAGED=<commit>/<version>`; don't use `DUCKDB_VERSION=alpha`, which always fetches the newest alpha.
- **AVX2 CPU required.** The 2.0 dev builds (wheel and CLI) crash with `Illegal instruction` on CPUs without AVX2. The homelab Incus server (Intel Pentium Silver J5005) has none, so the Incus stack can't run there until an official 2.0 release supports older CPUs. The Docker stack runs on any AVX2 machine.
- **HTTPS by default.** `CONNECT` uses HTTPS for any host other than localhost, but the server only speaks HTTP. `HYDROC_QUACK_DISABLE_SSL=true` adds `(DISABLE_SSL true)`.
- **Use `execute()`.** In Python, `con.sql()` resolves table names on the client and fails after `CONNECT`. `con.execute()` sends the statement to the server.
- **No bound parameters.** `?` values are not forwarded to the server, so values are rendered as SQL literals (`duck.literal`).
- **No TLS.** The listener speaks plain HTTP. Port 9494 stays on the private bridge; OpenTofu can publish it with `expose_quack_port`, but only do that behind a TLS proxy.
- **Localhost only by default.** `quack_serve` refuses a non-localhost address unless `allow_other_hostname = true` (set in `99_serve.sql`). If it fails, the CLI stays alive and the unit still reports `active`, so check the port (`ss -ltn | grep 9494`). Ansible does this with `wait_for`.

---

## Load modes

| Mode | Behaviour |
|------|-----------|
| `full` | Downloads the complete dataset into Raw, rebuilds Std from every Raw file, then rebuilds every Lake table of the dataset from every Std file. A watermark row is appended after each step (`raw`, `std`, `lake`). |
| `incremental` | First finishes a file left at `raw` or `std` by a failed run. Then downloads and compares against the latest watermark; only when new data exists: stores the file, converts it to Std and loads its changes into the Lake, with a watermark row after each step. |

Select what to run with `--datasets <code>` (repeatable) and/or `--sources <source>` (every dataset of a source); without either, every registered dataset runs.

---

## Infrastructure

Each setup lives in its own folder under `architecture/` and runs the same application code and the same `sql/ddl` scripts. Only how containers, buckets and credentials are provided differs.

| Folder | Setup | Notes |
|--------|-------|-------|
| `architecture/incus/` | Incus server: OpenTofu + Ansible | Real deployment target. Needs an AVX2 host for DuckDB 2.0 (see above). |
| `architecture/docker/` | Docker Compose with RustFS as S3 | Local or test deployment. See its [README](../architecture/docker/README.md). |

### Incus (`architecture/incus/`)

| Folder | Tool | Manages |
|--------|------|---------|
| `architecture/incus/tofu/` | OpenTofu + `lxc/incus` | Bridge `hydroc-br0`, project `hydroc`, profile, 6 buckets and their keys, 3 containers |
| `architecture/incus/ansible/` | Ansible, `community.general.incus` connection | Postgres catalogs and users, DuckDB server and its systemd unit, app venv and `.env` |

Ansible reads the bucket keys from `tofu output -json`, and the passwords and quack token from `group_vars/all/vault.yml`. The OpenTofu state, `*.tfvars`, `vault.yml` and `.env` are all git-ignored.

**Host prerequisites**
- `core.storage_buckets_address` must be set on the Incus server.
- For non-Ceph pools, the `minio` binary must be available to Incus.
- The containers reach the bucket endpoint as `https://<incus_host_name>:8555`. Ansible maps that name to the bridge gateway and trusts the Incus server certificate.
- Environment-specific values are kept out of git: `architecture/incus/tofu/terraform.tfvars` (Incus remote) and `architecture/incus/ansible/group_vars/all/local.yml` (Incus remote and host name, repository URL).

### Docker (`architecture/docker/`)

`compose.yaml` runs `rustfs` (S3 API with a web console), a one-shot `rustfs-init` that creates the buckets, `postgres` (catalog databases created by `postgres/init-catalogs.sh`), `duckdb` (the pinned 2.0 CLI, which mounts `sql/ddl` and renders `secrets.sql` from the environment in `entrypoint.sh`) and `app` (run on demand). Credentials come from `architecture/docker/.env`, which is git-ignored.

---

## Project structure

```
hydrocscraper/
├── main.py                 # CLI: full | incremental, --datasets / --sources
├── config.py               # Settings from .env, scraper registry
├── requirements.txt
├── .env.example
│
├── scrapers/
│   ├── base.py             # BaseScraper: modes, fetch_to_temp, store_raw/store_table, watermarks
│   └── npd/
│       └── field_production_monthly.py   # one class per source and dataset
├── storage/
│   ├── s3.py               # boto3 client for hydroc-raw
│   ├── raw.py              # Raw object keys and upload
│   ├── datasets.py         # tables of a dataset (data/static/datasets.csv)
│   ├── scripts.py          # finds and runs static SQL on the server
│   ├── std.py              # runs a dataset's Std SQL (Raw -> Std)
│   ├── duck.py             # quack client
│   ├── lake.py             # runs a table's Lake SQL (Std -> Lake)
│   └── watermark.py        # hook.metadata.watermark read/write
├── utils/
│   └── http.py             # HTTP client, retries
├── sql/ddl/                # DuckDB server startup script and DDL (raw/std views, Lake tables)
├── sql/std/                # Std scripts (Raw -> Std), per source and dataset
├── sql/lake/               # Lake load scripts, per source and table
├── data/static/            # static Hook metadata (CSV)
├── architecture/
│   ├── incus/
│   │   ├── tofu/           # OpenTofu (Incus)
│   │   └── ansible/        # Ansible roles: common, postgres, duckdb_server, app
│   └── docker/             # Docker Compose stack (RustFS, Postgres, DuckDB, app)
├── tests/                  # pytest
└── docs/
```
