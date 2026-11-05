# hydrocscraper on Docker

The same stack as the Incus setup, in Docker Compose. RustFS provides the S3 API.

| Service | What it does | Host access |
|---|---|---|
| `rustfs` | S3 server for the six `hydroc-<layer>` buckets | S3 API `http://127.0.0.1:9000`, console `http://127.0.0.1:9001/rustfs/console/index.html` |
| `rustfs-init` | One-shot job: creates the buckets, then exits | — |
| `postgres` | DuckLake catalogs `cat_hydroc_<layer>`, each owned by `user_hydroc_<layer>`; serving database `hydroc_serve` and Metabase's database `metabase` | — |
| `duckdb` | DuckDB 2.0 quack server running `sql/ddl/init_server.sql` | `quack:127.0.0.1:9494` |
| `metabase` | Metabase over `hydroc_serve.latest` (copies of the Library latest views) | `http://127.0.0.1:3000` |
| `metabase-init` | One-shot job: Metabase admin, database connection and Sodir dashboard (`../metabase/provision.py`), then exits | — |
| `app` | `main.py`, started on demand (repository mounted at `/app`) | — |

All ports are bound to `127.0.0.1` only. Data lives in named volumes (`rustfs-data`, `pg-data`).

**Requirements:** Docker with Compose v2, and a CPU with AVX2. The DuckDB 2.0 dev builds crash without AVX2.

## Start

```bash
cd architecture/docker
cp .env.example .env          # set every value; no single quotes
docker compose up -d --build  # rustfs, rustfs-init, postgres, duckdb, metabase, metabase-init
docker compose ps             # rustfs/postgres/duckdb/metabase healthy, rustfs-init and metabase-init exited (0)
```

## Run the app

```bash
docker compose run --rm app python main.py --mode full --sources no_sodir
docker compose run --rm app python main.py --mode incremental
```

`full` stores a new Raw file, rebuilds Std (`hydroc-std`) from every Raw file and rebuilds the Lake table (`lake.no_sodir.field_production_monthly`); `incremental` converts and loads a new file's changes only. The app creates a missing raw view, std view or Lake table itself.

Every load also refreshes the Metabase copies in `hydroc_serve`; `--mode serve` refreshes them alone:

```bash
docker compose run --rm app python main.py --mode serve
```

## Metabase

http://127.0.0.1:3000, signed in as `MB_ADMIN_EMAIL` / `MB_ADMIN_PASSWORD`: collection *hydroc*, dashboard *Sodir - Norwegian shelf production*. Setup, upgrade of an existing volume and design: [docs/metabase.md](../../docs/metabase.md).

After editing `data/static/*.csv`, restart the server so it rebuilds `hook.metadata.*`:

```bash
docker compose restart duckdb
```

## Inspect

- **Server log:** `docker compose logs duckdb`. On the very first start, only "No files found" errors from the raw and std views are expected.
- **Query the server from the app container:**
  ```bash
  docker compose run --rm app python -c "from storage import duck; print(duck.query('SELECT * FROM hook.metadata.watermark'))"
  ```
- **Buckets:** use the RustFS console at http://127.0.0.1:9001/rustfs/console/index.html (the bare `:9001/` returns 403), signing in with `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` from `.env`.
- **Catalogs:**
  ```bash
  docker compose exec postgres psql -U postgres -d cat_hydroc_hook -c '\dt'
  ```

## Stop

```bash
docker compose down        # keep the data
docker compose down -v     # also delete buckets and catalogs
```

## Differences from the Incus setup

- **Bucket keys:** a single RustFS root key serves all buckets; Incus uses one key per bucket.
- **S3 transport:** plain HTTP inside the Compose network (`USE_SSL false`), so no certificate handling is needed.
- **Server secrets:** `duckdb/entrypoint.sh` writes `secrets.sql` from environment variables at start; Incus uses an Ansible template.
- **Catalog setup:** `postgres/init-catalogs.sh` creates the catalog databases, but only when the data volume is empty (`postgres/init-serve.sh`, the serving databases, can be re-run by hand: see docs/metabase.md). After changing their passwords in `.env`, run `docker compose down -v`.
- **DuckDB build:** pinned with `DUCKDB_STAGED` in `duckdb/Dockerfile`. It must be the exact build of `duckdb==` in `requirements.txt`.
