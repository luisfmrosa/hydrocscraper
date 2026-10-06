---
name: add-frame
description: Add a Library frame to hydrocscraper — an SCD2 view over one Lake table with one HK_ column per hook of the dataset (library.frame.<code>[_dev]), plus its latest view with only the current, non-deleted versions (library.latest.<code>[_dev]), in development or production mode. Use when the user asks to add, create or rebuild a frame, a latest view or the Library objects of a dataset.
---

# Add a frame (Library)

Input: a dataset with a Lake table, i.e. a row of `data/static/datasets.csv` with keys (`code`, `keys`). For a non-tabular dataset, each flattened table is its own frame. The Lake table `lake.<source>.<table>` must exist (`lake-table` and `lake-load-script` skills).

A frame is a view over **one** Lake table (no joins). Each Lake row (new, changed or deleted) becomes one version; the hooks are added here, never in the Lake.

**Worked examples (tested):** development `sql/ddl/library/no_sodir_field_production_monthly_dev.sql` and `sql/ddl/library/no_sodir_field_dev.sql`; production (`integer` hook) `sql/ddl/library/no_sodir_field.sql`.

## 1. Ask

1. **Dataset:** which one (`code`). Below, `<code>` = `<source>_<table>`.
2. **Development or production?**

| | Development | Production |
|---|---|---|
| Frame view | `library.frame.<code>_dev` | `library.frame.<code>` |
| Latest view | `library.latest.<code>_dev` | `library.latest.<code>` |
| Script | `sql/ddl/library/<code>_dev.sql` | `sql/ddl/library/<code>.sql` |
| Hook expression | `hook_expression_dev` | `hook_expression_prod`, encoded per `hook_encoding` |
| Hook column | `VARCHAR`: `'<key_set>' \|\| '\|' \|\| (<hook_expression_dev>)::VARCHAR` | `BLOB`: `'<key_set_binary as \x escapes>'::BLOB \|\| <encoded value>` (below) |
| Sodir example | `no_sodir.field\|EKOFISK` | `integer`: `0x0801` + `0x0000A9F2` (EKOFISK, 43506) |

Production encoded value, as unsigned big-endian integers so the hex reads like the number (a negative or too large value fails the cast, so the view fails instead of building a wrong hook):

| `hook_encoding` | Encoded value | Hook bytes |
|---|---|---|
| `integer` | `unhex(printf('%08x', (<hook_expression_prod>)::UINTEGER))` | 2 + 4 |
| `bigint` | `unhex(printf('%016x', (<hook_expression_prod>)::UBIGINT))` | 2 + 8 |
| `varchar` | `encode((<hook_expression_prod>)::VARCHAR)` | 2 + length |

Development and production hooks may use different keys (Sodir: field name vs NPDID), so they don't always group rows the same way (a renamed field gets a new development hook).

Both modes can exist side by side (different names and files).

## 2. Get the hooks

```sql
SELECT h.id, bc.name, h.hook_expression_dev, h.hook_expression_prod, h.hook_encoding,
       h.key_set, hex(h.key_set_binary)
FROM hook.metadata.hooks h
JOIN hook.metadata.business_concepts bc ON bc.id = h.business_concept_id
JOIN hook.metadata.datasets d ON d.id = h.dataset_id
WHERE d.code = '<code>'
ORDER BY h.id
```

(or read `data/static/hooks.csv` and `business_concepts.csv`). Show them and ask the user to confirm, for each hook, the expression of the chosen mode (and the encoding in production). If they change one, update `hooks.csv` first (`add-hook` skill), so the file stays the single definition. If the dataset has no hook, say so and offer the `add-hook` skill; continue without hook columns only if the user agrees.

Write the key sets into the view as literals (static SQL). Production: `key_set_binary` `0801` → `'\x08\x01'::BLOB`.

## 3. Write the script

One file holds both views: `sql/ddl/library/<code>[_dev].sql`. Copy the worked example and replace the names, hook columns, data columns and keys.

**Frame**, `CREATE OR REPLACE VIEW library.frame.<code>[_dev] AS SELECT … FROM lake.<source>.<table>`, columns in this order:

1. **Hooks,** one per hook in hook `id` order, named `HK_` + the business concept's `name` in uppercase, any character other than a letter or digit replaced by `_` (`Field` → `HK_FIELD`). Value per the mode table. Use the mode's expression (`hook_expression_dev` or `hook_expression_prod`) and keep the parentheses around it.
2. **Data columns:** every data column of the Lake table, same names and order.
3. **Lineage:** `___Lake_md5`, `___Lake_datasource`, `___Lake_sourcefile`.
4. **SCD2 columns:**
   ```sql
   ___Lake_load_timestamp                                          AS ___Effective_From,
   lead(___Lake_load_timestamp, 1, 'infinity'::TIMESTAMPTZ) OVER (
       PARTITION BY <keys>
       ORDER BY ___Lake_load_timestamp
   )                                                               AS ___Effective_To,
   ___Lake_isdeleted                                               AS ___Is_Deleted
   ```
   `___Effective_From` is when the version was observed (the Raw file's download time). The key's last version is open: `___Effective_To` is `'infinity'::TIMESTAMPTZ`, the same type as the `LEAD` values.

   **Never use a `9999-12-31` literal for the open end.** A `TIMESTAMPTZ` literal without an offset is read in the session's time zone: the server (UTC) and a client in another zone would build different moments, and a query like `WHERE ___Effective_To = TIMESTAMPTZ '9999-12-31'` from that client would silently match nothing. `infinity` has no time zone. Query open versions with `___Effective_To = 'infinity'::TIMESTAMPTZ` or `NOT isfinite(___Effective_To)`. Outside SQL it shows oddly: Python `fetchall()` gives `datetime(9999, 12, 31, 23, 59, 59, 999999)` without a time zone, pandas gives `294247-01-10 04:00:54+00:00`.

   List every key column in `PARTITION BY` (`parent` included for a flattened table).

**Latest**, current versions only:

```sql
CREATE OR REPLACE VIEW library.latest.<code>[_dev] AS
SELECT * EXCLUDE (___Effective_From, ___Effective_To, ___Is_Deleted)
FROM library.frame.<code>[_dev]
WHERE ___Effective_To = 'infinity'::TIMESTAMPTZ
  AND NOT ___Is_Deleted;
```

A key whose last version is a deletion has an open `___Effective_To` but `___Is_Deleted = true`, so it's excluded.

Header comment: both view names, the source Lake table, the business key, the mode, each hook (column, id, key set, expression) and the meaning of the SCD2 columns, as in the example.

## 4. Register

Add `.read library/<code>[_dev].sql` to `sql/ddl/init_server.sql`, under `-- Library frame and latest views`. At server start it fails harmlessly while the Lake table doesn't exist; `storage/lake.py` re-runs it after every Lake load of the table (it finds `<code>.sql` and `<code>_dev.sql` by name), so no restart is needed.

## 5. Verify

1. **Tests:** like `tests/test_library.py` (it reuses the Lake fixtures of `tests/test_lake.py`): versions and effective ranges, a key deleted and back, a key deleted last, one open version per key, hook values, `latest` columns and rows, and the same results under a non-UTC session time zone. Run `pytest` in the app container (`docker compose run --rm --no-deps app sh -c "pip install -q pytest && python -m pytest -q"`).
2. **Docker stack** (`architecture/docker`): `docker compose restart duckdb` (no error in `docker compose logs duckdb` once the Lake table exists), then `docker compose run --rm app python main.py --mode full --datasets <dataset code>` (the log shows the library script after the load). Then:
   ```sql
   -- one frame row per Lake row
   SELECT (SELECT count(*) FROM library.frame.<code>[_dev]), (SELECT count(*) FROM lake.<source>.<table>);
   -- latest = keys whose last Lake row is not a deletion
   SELECT (SELECT count(*) FROM library.latest.<code>[_dev]),
          (SELECT count(*) FROM (SELECT * FROM lake.<source>.<table>
                                 QUALIFY row_number() OVER (PARTITION BY <keys> ORDER BY ___Lake_load_timestamp DESC) = 1)
           WHERE NOT ___Lake_isdeleted);
   -- exactly one open version per key: must return 0
   SELECT count(*) FROM (SELECT 1 FROM library.frame.<code>[_dev] WHERE ___Effective_To = 'infinity'::TIMESTAMPTZ
                         GROUP BY <keys> HAVING count(*) <> 1);
   -- no NULL hook: must return 0
   SELECT count(*) FROM library.frame.<code>[_dev] WHERE HK_<NAME> IS NULL;
   ```
   Production: also check `hex(HK_<NAME>)` starts with the hook's `hex(key_set_binary)` and every hook has the encoding's length (`octet_length(HK_<NAME>)` = 6 for `integer`, 10 for `bigint`).

## Changing a frame

The views are `CREATE OR REPLACE`: edit the script and restart the server or run a load. After a hook is added or its expression changes, update the dataset's frame script(s) here. Nothing in the Lake changes.
