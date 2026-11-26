---
name: add-frame
description: Add a Library frame to hydrocscraper — an SCD2 view over one Lake table with one HK_ column per hook of the dataset (library.frame.<code>[_dev]), plus its latest view with only the current, non-deleted versions (library.latest.<code>[_dev]), as dbt models in transform/. Use when the user asks to add, create or rebuild a frame, a latest view or the Library objects of a dataset.
---

# Add a frame (Library)

Input: a dataset with a Lake table, i.e. a row of `data/static/datasets.csv` with keys (`code`, `keys`). For a non-tabular dataset, each flattened table is its own frame. The Lake table `lake.<source>.<table>` must exist (`lake-table` and `lake-load-script` skills).

A frame is a view over **one** Lake table (no joins). Each Lake row (new, changed or deleted) becomes one version; the hooks are added here, never in the Lake.

The Library is a dbt project (`transform/`, see `transform/README.md`). The SQL is not written by hand: `transform/macros/library.sql` generates it from `hook.metadata.hooks` and `hook.metadata.datasets`, so `hooks.csv` and `datasets.csv` are the only definitions. **Worked example (tested):** `transform/models/library/no_sodir_field/` (two hooks, `HK_FIELD` and `HK_COMPANY__Operator`, the second NULL for fields without an operator).

## 1. Check the hooks

Below, `<code>` = `<source>_<table>`.

```sql
SELECT h.id, h.hook_column, h.hook_expression_dev, h.hook_expression_prod, h.hook_encoding,
       h.key_set, hex(h.key_set_binary)
FROM hook.metadata.hooks h
JOIN hook.metadata.datasets d ON d.id = h.dataset_id
WHERE d.code = '<code>'
ORDER BY h.id
```

(or read `data/static/hooks.csv`). Show them to the user. If one is missing or wrong, fix `hooks.csv` first (`add-hook` skill) and restart the server so `hook.metadata.hooks` follows it. A dataset without hooks can't have a frame: `hook_frame` fails. Offer the `add-hook` skill.

What the macro builds, per mode:

| | Development | Production |
|---|---|---|
| Frame view | `library.frame.<code>_dev` | `library.frame.<code>` |
| Latest view | `library.latest.<code>_dev` | `library.latest.<code>` |
| Hook column | `VARCHAR`: `'<key_set>' \|\| '\|' \|\| (<hook_expression_dev>)::VARCHAR` | `BLOB`: `unhex('<key_set_binary hex>') \|\| <hook_expression_prod encoded per hook_encoding>` |
| Sodir example | `no_sodir.sup.field\|EKOFISK` | `integer`: `0x080101` + `0x0000A9F2` (EKOFISK, 43506) |

Encodings (`integer` 4 bytes, `bigint` 8, `varchar` UTF-8) are unsigned and big-endian; a negative or too large value fails the cast, so the view fails instead of building a wrong hook. Development and production hooks may use different keys (Sodir: field name vs NPDID), so they don't always group rows the same way.

Frame columns: the hooks (hook `id` order, named by `hook_column`), the Lake table's data columns and lineage (`___Lake_md5`, `___Lake_datasource`, `___Lake_sourcefile`), then `___Effective_From` (`___Lake_load_timestamp`), `___Effective_To` (`lead(...)` over the dataset's `keys`, `'infinity'::TIMESTAMPTZ` for the open version: never a `9999-12-31` literal, which depends on the session time zone) and `___Is_Deleted`. Latest: the frame's open, non-deleted versions, without those three columns.

## 2. Add the models

1. Add the Lake table to `transform/models/library/sources.yml`, under its source (`database: lake`, `schema: <source>`).
2. Create `transform/models/library/<code>/` with four one-line models (both modes, always: `tests/test_hook_static.py` checks every hooked dataset has all four):

   | File | Content |
   |---|---|
   | `frame_<code>.sql` | `{{ hook_frame('<source>', '<table>', 'prod') }}` |
   | `frame_<code>_dev.sql` | `{{ hook_frame('<source>', '<table>', 'dev') }}` |
   | `latest_<code>.sql` | `{{ hook_latest(ref('frame_<code>')) }}` |
   | `latest_<code>_dev.sql` | `{{ hook_latest(ref('frame_<code>_dev')) }}` |

   The `frame_`/`latest_` prefix gives the schema and the rest the view name (`transform/macros/naming.sql`).

Nothing to register: `storage/lake.py` builds the folder's models after every Lake load of the table (`storage/library.py`), and DuckLake keeps the views across server restarts.

## 3. Verify

1. **Tests:** like `tests/test_library.py` (it reuses the Lake fixtures of `tests/test_lake.py` and builds the models with dbt through `tests/library_dbt.py`): versions and effective ranges, a key deleted and back, a key deleted last, one open version per key, hook values, `latest` columns and rows, and the same results under a non-UTC session time zone. Run `pytest` in the app container (`docker compose run --rm --no-deps app sh -c "pip install -q pytest && python -m pytest -q"`).
2. **Docker stack** (`architecture/docker`): `docker compose run --rm app python main.py --mode full --datasets <dataset code>` (the log shows `dbt run --select path:models/library/<code>` after the load), or only the views: `docker compose run --rm app python -m storage.library run --select path:models/library/<code>`. Then:
   ```sql
   -- one frame row per Lake row
   SELECT (SELECT count(*) FROM library.frame.<code>[_dev]), (SELECT count(*) FROM lake.<source>.<table>);
   -- exactly one open version per key: must return 0
   SELECT count(*) FROM (SELECT 1 FROM library.frame.<code>[_dev] WHERE ___Effective_To = 'infinity'::TIMESTAMPTZ
                         GROUP BY <keys> HAVING count(*) <> 1);
   -- no NULL hook where the expression has a value: must return 0 (a NULL hook is
   -- accepted only where the hook expression itself is NULL, agreed in add-hook)
   SELECT count(*) FROM library.frame.<code>[_dev] WHERE HK_<NAME> IS NULL AND (<hook expression of the mode>) IS NOT NULL;
   ```
   Production: also check `hex(HK_<NAME>)` starts with the hook's `hex(key_set_binary)` and every hook has the encoding's length (`octet_length(HK_<NAME>)` = 7 for `integer`, 11 for `bigint`).

## Changing a frame

There is nothing per dataset to edit: after a hook is added or changed in `hooks.csv` (or a dataset's `keys`), restart the server (it rebuilds `hook.metadata.*`), then rebuild the views: `python -m storage.library run` (every model) or `--select path:models/library/<code>`. A change to what every frame looks like goes in `transform/macros/library.sql`, and is tested by the whole suite. Nothing in the Lake changes.
