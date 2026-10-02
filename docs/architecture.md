# Architecture

## Overview

hydrocscraper collects official hydrocarbon production data from multiple sources and organises it in layers following the Hook methodology. The stack is cloud-ready: object storage uses the S3 API, catalogs live in Postgres, and DuckDB runs as a server in a container. The design rationale is in [architecture_v2.md](architecture_v2.md).

The same stack can be deployed two ways (see *Infrastructure* below): on an Incus server (`architecture/incus/`) or with Docker Compose (`architecture/docker/`). The diagram shows the Incus layout; in Docker the containers are `app`, `duckdb`, `postgres` and `rustfs`.

```
                         Incus project "hydroc"  (bridge hydroc-br0, 10.10.40.0/24)

  ┌───────────────┐   boto3 (raw files)     ┌──────────────────────────────────────┐
  │  hydroc-app   │────────────────────────▶│ Incus S3 buckets (<incus-host>:8555) │
  │  main.py      │                         │ hydroc-raw  hydroc-lake              │
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
| `hydroc-app` | Runs the scrapers (`main.py`). It uploads raw files to `hydroc-raw` and reads and writes metadata through the quack server. It holds no catalog credentials. |
| `hydroc-duckdb` | DuckDB CLI server. It attaches the four DuckLakes, applies the DDL in `sql/ddl/` at startup and serves the quack protocol. |
| `hydroc-pg` | PostgreSQL. It holds one DuckLake catalog database per layer: `cat_hydroc_<layer>`, owned by `user_hydroc_<layer>`. |
| S3 buckets | One bucket per layer, `hydroc-<layer>`. Incus storage buckets (one key per bucket) or RustFS in Docker (one root key). |

---

## Layers

| Layer | Storage | Contents |
|-------|---------|----------|
| **Raw** | `hydroc-raw` (plain bucket) | Files exactly as received, plus `metadata/` (known sources) |
| **Lake** | DuckLake `lake` | Denormalised, append-only change records. *Planned.* |
| **Library** | DuckLake `library`, schemas `frame` and `latest` | SCD2-like Frame objects and latest-version views. *Planned.* |
| **DWH** | DuckLake `dwh`, schema `supply` | Business views and models |
| **Hook** | DuckLake `hook`, schemas `metadata` and `raw_views` | Hook metadata (`watermark`, …) and views over Raw files |

### Raw bucket layout

```
hydroc-raw/
├── <source>/<dataset>/year_month=<YYYY-MM>/<stem>_<YYYYMMDD_HHmm><ext>
│     e.g. npd/field_production_monthly/year_month=2026-09/field_production_monthly_20260929_1000.csv
└── metadata/
    └── known_sources/known_sources_<YYYYMMDD_HHmm>.json
```

- `year_month` defaults to the UTC month of the download. A scraper may pass the reference period instead, for sources that publish one file per period.
- Every download gets its own timestamped file, so nothing is overwritten.

### Watermarks

`hook.metadata.watermark` is append-only and gets one row per successful load:

| Column | Description |
|--------|-------------|
| `source`, `dataset` | For example `npd`, `field_production_monthly` |
| `load_mode` | `full` or `incremental` |
| `last_period_fetched` | `YYYY-MM` |
| `status` | `ok` |
| `raw_file` | Object key in `hydroc-raw` |
| `updated_at` | UTC timestamp |

`hook.metadata.watermark_latest` returns the most recent row per `(source, dataset)`.

---

## DuckDB server

`sql/ddl/init_server.sql` is the server's entry point, and it runs at every start of `duckdb-quack.service`:

```
.bail off                        -- keep going if a raw view has no files yet
00_extensions.sql                -- httpfs, postgres, ducklake, quack
/opt/duckdb/secrets.sql          -- rendered by Ansible: S3 + DuckLake secrets, quack token
10_attach.sql                    -- ATTACH 'ducklake:ducklake_<layer>' AS <layer>
20_library.sql … 41_*.sql        -- schemas, watermark table/view (IF NOT EXISTS)
raw_views/*.sql                  -- hook.raw_views.* over s3://hydroc-raw/...
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
| `full` | Downloads the complete history, stores it in the Raw bucket, and appends a watermark row |
| `incremental` | Downloads and compares against the latest watermark. It stores the file and appends a row only when new data exists. |
| `discover` | Writes a new `known_sources_<ts>.json` snapshot with `md5_digest` per record. `--seed FILE` imports a local catalog. |

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
| `architecture/incus/tofu/` | OpenTofu + `lxc/incus` | Bridge `hydroc-br0`, project `hydroc`, profile, 5 buckets and their keys, 3 containers |
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
├── main.py                 # CLI: full | incremental | discover
├── config.py               # Settings from .env, scraper registry
├── requirements.txt
├── .env.example
│
├── scrapers/
│   ├── base.py             # BaseScraper: fetch_to_temp, store_raw, watermarks
│   └── npd.py              # Norway Sokkeldirektoratet
├── models/production.py    # Unified record shape (future dwh.supply)
├── storage/
│   ├── s3.py               # boto3 client for hydroc-raw
│   ├── raw.py              # Raw object keys and upload
│   ├── duck.py             # quack client
│   └── watermark.py        # hook.metadata.watermark read/write
├── discovery/store.py      # known_sources snapshots in the Raw bucket
├── utils/
│   ├── http.py             # HTTP client, retries
│   └── hashing.py          # row_md5 (md5_digest)
├── sql/ddl/                # DuckDB server startup script and DDL
├── architecture/
│   ├── incus/
│   │   ├── tofu/           # OpenTofu (Incus)
│   │   └── ansible/        # Ansible roles: common, postgres, duckdb_server, app
│   └── docker/             # Docker Compose stack (RustFS, Postgres, DuckDB, app)
├── tests/                  # pytest
└── docs/
```
