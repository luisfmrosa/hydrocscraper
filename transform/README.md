# transform — dbt project

The Library layer (`library.frame.*`, `library.latest.*`) as dbt models, run on
the DuckDB quack server. Design and constraints: `docs/architecture.md`,
sections *Library views* and *dbt*.

```
dbt_project.yml        models/library -> database library, views
profiles.yml           target quack: everything runs on the server (env: HYDROC_QUACK_*)
macros/library.sql     hook_frame(source, table, mode), hook_latest(frame)
macros/naming.sql      frame_<code>[_dev] -> library.frame.<code>[_dev], latest_ likewise
macros/drop_relation.sql  DROP without CASCADE (DuckLake)
models/library/sources.yml       the Lake tables
models/library/<code>/*.sql      four one-line models per Lake table
```

## Running

From the repository root, with the app's environment (`.env`):

```bash
python -m storage.library run                                         # every model
python -m storage.library run --select path:models/library/no_sodir_field
python -m storage.library compile --select frame_no_sodir_field       # SQL in transform/target/compiled/
```

`python -m storage.library` passes its arguments to dbt with this project and
profile and puts the repository on the import path (the profile loads the
quack plugin `storage.dbt_quack`). The pipeline calls it after every Lake load
(`storage/lake.py`). Docker: `docker compose run --rm app python -m storage.library run`.

The plain dbt CLI works too: `cd transform && PYTHONPATH=.. dbt run --profiles-dir .`
(with `HYDROC_QUACK_URL`, `HYDROC_QUACK_TOKEN` and `HYDROC_QUACK_DISABLE_SSL` set).

Compiling needs the server: the macros read `hook.metadata.hooks` and
`hook.metadata.datasets`.

## Adding a frame

Project skill `add-frame`: add the Lake table to `models/library/sources.yml`
and four one-line models in `models/library/<code>/`. Hook columns come from
`data/static/hooks.csv`; nothing is written by hand.

## Not used

- **Seeds.** `dbt seed` runs `COPY … FROM '<client path>'` on the server, where
  the path doesn't exist. Static metadata stays in `sql/ddl/45_hook_static.sql`.
- **dbt-core 1.12.** 1.12.7 failed to start with dbt-duckdb 1.11.1
  (`ModuleNotFoundError` in `metricflow_semantic_interfaces`); pinned to 1.11.x.
