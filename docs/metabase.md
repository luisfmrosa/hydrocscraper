# Serving layer: Metabase

Metabase is the analytical front end over the Library layer. It reads **copies of the Library latest views** (`library.latest.*`) kept in a plain Postgres database, `hydroc_serve`, through its built-in Postgres driver.

```
library.latest.<code>[_dev]  ──sql/serve/<source>/<table>.sql──▶  hydroc_serve.latest.<code>[_dev]  ──▶  Metabase
   (DuckLake, DuckDB server)        (run by the DuckDB server)         (Postgres)                        (built-in Postgres driver)
```

## Why a Postgres copy, not a direct DuckDB connection

- The Library lives behind the DuckDB 2.0 dev build and its quack protocol. No Metabase driver speaks quack.
- The community Metabase DuckDB driver bundles a stable DuckDB. To use it, Metabase would have to attach the four DuckLake catalogs itself, with another `ducklake` extension version than the server's. That risks a catalog-version mismatch or an unwanted catalog migration, and it would need every catalog and S3 credential on the Metabase host.
- A Postgres copy needs no plugin. Metabase only gets read access to one schema, and the DuckDB build can change without touching Metabase.

Data is small (Sodir: about 31,500 rows per mode, in 6 production and 6 development tables), so each refresh replaces every table in full.

## How the copies are kept current

| Piece | Role |
|---|---|
| `sql/ddl/10_attach.sql` | `ATTACH '' AS serve (TYPE postgres, SECRET pg_serve)` at server start. The `pg_serve` secret is rendered into `secrets.sql` (Docker `entrypoint.sh`, Incus `secrets.sql.j2`). |
| `sql/serve/<source>/<table>.sql` | One per Lake table with Library views: in a single Postgres transaction, `DROP TABLE IF EXISTS` + `CREATE TABLE serve.latest.<code>[_dev] AS SELECT * FROM library.latest.<code>[_dev]`. Readers see either the old copy or the new one. |
| `storage/serve.py` | Runs a table's serve script. Called by `storage/lake.py` after every Lake load, once the Library views have been recreated. |
| `python main.py --mode serve` | Refreshes the copies only, with no download or load (e.g. to fill a new `hydroc_serve`). Accepts `--datasets` / `--sources`. |

Postgres types: production hooks (`BLOB`) become `bytea`, development hooks stay `varchar`. Data columns keep their types. Column names keep their case, so quote them in SQL (`"prfYear"`).

**Access.** `hydroc_serve` is owned by `user_hydroc_serve`, the only user the DuckDB server writes with. Metabase connects as `user_metabase`, which owns Metabase's own application database `metabase` and can only `SELECT` from `hydroc_serve.latest`. That access comes from default privileges, so it survives the drop and recreate on every refresh.

**Adding a dataset.** When you add Library views for a new Lake table (`add-frame` skill), also add `sql/serve/<source>/<table>.sql`. Copy an existing one: it lists the production view, then the development view. `tests/test_serve.py` fails for a Library table that has no serve script.

## The dashboard

`architecture/metabase/provision.py` (standard library only) uses the Metabase API. It is idempotent: each run updates objects in place, found by name.

1. It runs the first-run setup with the admin `MB_ADMIN_EMAIL` / `MB_ADMIN_PASSWORD`. On later runs it logs in with them.
2. It adds the database connection **hydroc serve**: `hydroc_serve`, schema `latest` only, as `user_metabase`.
3. It creates the collection **hydroc** and the dashboard **Sodir - Norwegian shelf production**. The dashboard has 9 native SQL questions over `latest.no_sodir_*`, all production mode:
   - KPIs: oil equivalent over the last 12 months, producing fields in the latest month, latest production month, remaining reserves.
   - Monthly net production by product (oil, gas, NGL, condensate), from 1971 on.
   - Top 15 fields, last 12 months.
   - Production by current operator, last 12 months (joins `no_sodir_field`).
   - Remaining reserves by company, top 15.
   - Fields by current activity status.

"Last 12 months" means the 12 latest months in the data, since Sodir runs a few months behind. The questions show an error until the first load has filled the copies.

New tables appear in Metabase's query builder after its next schema sync (hourly), or right away when you re-run the provisioning (it triggers a sync).

## Deploy with Docker

```bash
cd architecture/docker
cp .env.example .env    # also set PG_PASSWORD_SERVE, PG_PASSWORD_METABASE, MB_ADMIN_EMAIL, MB_ADMIN_PASSWORD
docker compose up -d --build
docker compose run --rm app python main.py --mode full     # load Sodir; refreshes hydroc_serve
```

- Metabase: http://127.0.0.1:3000. Sign in with `MB_ADMIN_EMAIL` / `MB_ADMIN_PASSWORD` and open *hydroc → Sodir - Norwegian shelf production*.
- Metabase is part of the same Compose project (`hydroc`) as the rest of the stack, with two one-shot helpers that run on every `up` and exit 0:
  - `postgres-serve-init` creates `hydroc_serve`, `metabase`, their users and grants (idempotent, `postgres/init-serve.sh`). Both `duckdb` and `metabase` wait for it.
  - `metabase-init` runs `provision.py`. To re-run it by hand: `docker compose run --rm metabase-init`.
- **Adding Metabase to an existing stack** (data volumes created before this change): add the four new values to `.env`, then:
  ```bash
  docker compose up -d --build                             # creates the serving databases, recreates duckdb (attaches serve), starts metabase
  docker compose run --rm app python main.py --mode serve  # fill the copies from the current Library
  ```
  Existing buckets, catalogs and Lake data are kept.
- Metabase version: `METABASE_VERSION` in `.env` (default `v0.65.3.3` in `compose.yaml`).

## Deploy on Incus

1. **Vault.** In `group_vars/all/vault.yml`, add `vault_pg_passwords.serve`, `vault_pg_passwords.metabase`, `vault_metabase_admin_email` and `vault_metabase_admin_password` (see `vault.yml.example`).
2. **OpenTofu.**
   ```bash
   cd architecture/incus/tofu
   tofu apply
   ```
   This creates the container `hydroc-metabase` (10.10.40.40) and a proxy device that publishes Metabase on host port `expose_metabase_port` (default 3000; 0 = not published).
3. **Ansible.**
   ```bash
   cd ../ansible
   ansible-playbook site.yml
   ```
   - The `postgres` role creates `user_hydroc_serve`, `user_metabase`, the databases `hydroc_serve` and `metabase`, the schema `latest`, the grants, and `pg_hba` entries limited to `hydroc-duckdb` and `hydroc-metabase`.
   - The `duckdb_server` role adds the `pg_serve` secret and restarts the server.
   - The new `metabase` role installs Temurin 25 JRE (Adoptium apt repository) and the OSS jar `metabase_version` as the systemd unit `metabase`, waits for `/api/health`, then runs `provision.py` inside the container.
4. **First data.** On `hydroc-app`, run `python main.py --mode serve` (or the next full or incremental load).
5. **Open Metabase.** Go to `http://<incus-host>:3000`.

Operations:

- Logs: `incus exec hydroc-metabase --project hydroc -- journalctl -u metabase -f`.
- Upgrade: change `metabase_version` in `vars.yml` and `METABASE_VERSION` in `compose.yaml`, then re-run Ansible. The new jar is downloaded next to the old one, and Metabase migrates its application database at start.
- Back up: Metabase's state is the Postgres database `metabase`. `hydroc_serve` can always be rebuilt with `--mode serve`.
