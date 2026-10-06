---
name: add-hook
description: Add a hook to hydrocscraper — tie a business concept to a dataset with a hook expression in data/static/hooks.csv (adding the business concept to business_concepts.csv if it's new), then check the derived key_set and key_set_binary on the server. Use when the user asks to add, define or register a hook or a business concept for a dataset.
---

# Add a hook

A hook ties a **business concept** to a **dataset**, through a **hook expression** that gives the concept's business key in that dataset. `data/static/hooks.csv` stores only:

| Column | Content |
|---|---|
| `id` | Integer, the next one (max existing `id` + 1) |
| `business_concept_id` | → `business_concepts.csv` `id` |
| `dataset_id` | → `datasets.csv` `id` |
| `hook_expression` | SQL expression over the dataset's std view columns, e.g. `prfNpdidInformationCarrier` |

The hook identifiers are **not** in the file. `sql/ddl/45_hook_static.sql` derives them at each server start:
- `key_set` = `<source code>.<business concept code>` (the dataset's source), e.g. `no_sodir.field`;
- `key_set_binary` = source id as one byte || business concept id as one byte, e.g. `0x0801`.

Never add `key_set` columns to the CSV. Hooks are metadata for the **Library** layer, where the frame views carry them as `HK_<NAME>` columns (`add-frame` skill). They never go into Lake tables, which hold only incremental changes: adding a hook changes no Lake table or load script.

## 1. Ask for the input

Ask the user, unless already given:
1. **Dataset:** which one. Show the candidates from `data/static/datasets.csv` (`id`, `code`). A hook goes on a row that has a Std/Lake table (non-empty `keys`); for a non-tabular dataset that means one of its flattened tables, not the downloaded dataset's own row.
2. **Business concept:** which one. Show `data/static/business_concepts.csv` (`id`, `code`, `name`). If it's new, also ask for its `code` (lowercase, short, no dots or spaces: it becomes part of `key_set`), `name` and `description`.
3. **Hook expression:** which expression of the dataset gives the concept's business key. Show the dataset's columns (the std view `sql/ddl/std_views/*_<dataset code>.sql` and the Lake table have the same ones; on the server, `DESCRIBE hook.std_views.<code>`) and suggest the likely one. It is usually one column (`prfNpdidInformationCarrier`); it may be an expression over several (`concat_ws('-', country, field)`), using those column names only.

## 2. Check before writing

Stop and tell the user if any of these fails:
- the dataset `id` and business concept `id` exist (or the concept is being added now);
- the dataset's `source_id` and the business concept `id` are both **≤ 255** (one byte each in `key_set_binary`). A new business concept takes the next `id`; if that would be 256, raise it with the user (the binary format would have to change);
- no row in `hooks.csv` already has the same (`business_concept_id`, `dataset_id`): one column per concept in the Lake table;
- the business concept `code` is unique in `business_concepts.csv`;
- the hook expression is valid on the std view and never NULL (the hook must identify every row):
  ```sql
  SELECT count(*) FILTER ((<hook expression>) IS NULL), count(DISTINCT (<hook expression>)) FROM hook.std_views.<code>
  ```
  The first count must be 0. If the std view doesn't exist yet (new dataset), check the expression against the Std script's columns and run the query once data is loaded.

Datasets of the same source share `key_set` for a given concept (`no_sodir.field` for every Sodir dataset). That's intended: it's how their rows meet on the hook. Mention it if the user expects one key set per dataset.

## 3. Write

- New business concept: append `<next id>,<code>,<name>,<description>` to `data/static/business_concepts.csv` (quote fields containing commas).
- Append `<next id>,<business_concept_id>,<dataset_id>,<hook_expression>` to `data/static/hooks.csv`. Quote the expression if it contains a comma or a quote (`"concat_ws('-', a, b)"`).

Keep the existing rows and their order; ids are never reused or renumbered.

## 4. Verify

1. `pytest tests/test_hook_static.py` (in the app container: `docker compose run --rm --no-deps app sh -c "pip install -q pytest && python -m pytest -q tests/test_hook_static.py"`, from `architecture/docker`). It builds the hooks from the real CSVs.
2. On the Docker stack: `docker compose restart duckdb`, then `docker compose logs duckdb --since 1m | grep -i error` must show nothing about hooks (a bad row fails the build and keeps the previous table).
3. Check the derived identifiers:
   ```bash
   docker compose run --rm app python -c "from storage import duck; print(duck.query('SELECT id, hook_expression, key_set, hex(key_set_binary) FROM hook.metadata.hooks ORDER BY id')[1])"
   ```
   The new row must show its expression, `<source code>.<concept code>` and `<source id as 2 hex digits><concept id as 2 hex digits>`.

## Report

Tell the user the new hook's `id`, `hook_expression`, `key_set` and `key_set_binary`, and any business concept added. The dataset's frame views don't pick the hook up by themselves (they are static SQL): if the dataset has frames (`sql/ddl/library/<code>[_dev].sql`), offer to update them with the `add-frame` skill; otherwise offer to create them.
