---
name: add-hook
description: Add a hook to hydrocscraper — tie a business concept to a dataset with a development and a production hook expression and a production encoding in data/static/hooks.csv (adding the business concept to business_concepts.csv, in a business domain, if it's new), then check the derived key_set and key_set_binary on the server. Use when the user asks to add, define or register a hook or a business concept for a dataset.
---

# Add a hook

A hook ties a **business concept** to a **dataset**, through **hook expressions** that give the concept's business key in that dataset: one for the development Library views, one for production. `data/static/hooks.csv` stores only:

| Column | Content |
|---|---|
| `id` | Integer, the next one (max existing `id` + 1) |
| `business_concept_id` | → `business_concepts.csv` `id` |
| `dataset_id` | → `datasets.csv` `id` |
| `hook_expression_dev` | SQL expression over the dataset's columns, used as text in development: usually a readable key, e.g. `prfInformationCarrier` (field name) |
| `hook_expression_prod` | SQL expression over the dataset's columns for production: usually the source's id, e.g. `prfNpdidInformationCarrier` |
| `hook_encoding` | How the production value is encoded after `key_set_binary`: `integer` (4 bytes, 0 to 4,294,967,295), `bigint` (8 bytes; the default when empty) or `varchar` (UTF-8 text). Integers are unsigned and big-endian |
| `hook_role` | Optional: the role the concept plays in the dataset, an uppercase letter then letters or digits (`Operator`: a field's operator company). Empty when the concept appears in one way only. It names the frame column (`HK_COMPANY__Operator`) and lets a dataset hook the same concept once per role; it doesn't change the key set |

The hook identifiers are **not** in the file. `sql/ddl/45_hook_static.sql` derives them at each server start:
- `key_set` = `<source code>.<business domain code>.<business concept code>` (the dataset's source, the concept's domain), e.g. `no_sodir.sup.field`;
- `key_set_binary` = source id || business domain id || business concept id, one byte each, e.g. `0x080101`.

`hook_column` is derived too: `HK_` + the business concept's name in uppercase (any character other than a letter or digit → `_`), then `__<hook_role>` if any (`HK_FIELD`, `HK_COMPANY__Operator`).

Never add `key_set` or `hook_column` columns to the CSV. Hooks are metadata for the **Library** layer, where the frame views carry them as `HK_<NAME>` columns (`add-frame` skill). They never go into Lake tables, which hold only incremental changes: adding a hook changes no Lake table or load script.

## 1. Ask for the input

Ask the user, unless already given:
1. **Dataset:** which one. Show the candidates from `data/static/datasets.csv` (`id`, `code`). A hook goes on a row that has a Std/Lake table (non-empty `keys`); for a non-tabular dataset that means one of its flattened tables, not the downloaded dataset's own row.
2. **Business concept:** which one. Show `data/static/business_concepts.csv` (`id`, `code`, `name`). If it's new, also ask for its `code` (lowercase, short, no dots or spaces: it becomes part of `key_set`), `name`, `description` and **business domain**: one of `data/static/business_domains.csv` (`id`, `code`, `name`), or a new one added first with the `add-business-domain` skill. Tell the user the domain is final: it is part of every hook of the concept, so it never changes once a hook uses the concept (to move a concept, create a new one).
3. **Hook expressions:** which expression of the dataset gives the concept's business key, for **development** and for **production**. Show the dataset's columns (the std view `sql/ddl/std_views/*_<dataset code>.sql` and the Lake table have the same ones; on the server, `DESCRIBE hook.std_views.<code>`) and suggest the likely ones: a readable column (a name) for development, the source's id for production. Each is usually one column; it may be an expression over several (`concat_ws('-', country, field)`), using those column names only. The same expression for both is fine.
4. **Encoding** of the production value: `integer` unless the user says otherwise and the values fit (non-negative, ≤ 4,294,967,295); `bigint` for larger integers; `varchar` for a key that isn't an integer. If other hooks already use the same key set (same source and concept), the encoding is theirs: say so instead of asking.
5. **Role:** does the concept play a specific role in the dataset (a field's operator, a licence's licensee…)? Ask whenever the concept could appear in the dataset in more than one role, so the column says which one; suggest a short name in title case (`Operator`, `Licensee`). Leave it empty when the concept appears in one way only (`Field` in a fields dataset).

## 2. Check before writing

Stop and tell the user if any of these fails:
- the dataset `id` and business concept `id` exist (or the concept is being added now);
- the dataset's `source_id`, the business domain `id` and the business concept `id` are all **≤ 255** (one byte each in `key_set_binary`). A new business concept takes the next `id`; if that would be 256, raise it with the user (the binary format would have to change);
- no row in `hooks.csv` already has the same (`business_concept_id`, `dataset_id`, `hook_role`): one hook column per concept and role in a frame. A second hook of the same concept in a dataset needs a different role (and the existing one may then need a role too: ask);
- the role, if any, is an uppercase letter followed by letters or digits;
- the business concept `code` is unique in `business_concepts.csv` (concept ids and codes are unique across domains), and its `business_domain_id` exists in `business_domains.csv`;
- the encoding is the same as every other hook of the same key set (the server rejects mixed encodings: their production hooks could never match);
- both expressions are valid on the std view, NULL only where the business key is genuinely absent, and the production one fits its encoding:
  ```sql
  SELECT count(*) FILTER ((<dev expression>) IS NULL),
         count(*) FILTER ((<prod expression>) IS NULL),
         count(DISTINCT (<dev expression>)), count(DISTINCT (<prod expression>)),
         count(DISTINCT ((<dev expression>), (<prod expression>))),
         min((<prod expression>)::UINTEGER), max((<prod expression>)::UINTEGER)   -- integer; UBIGINT for bigint
  FROM hook.std_views.<code>
  ```
  The casts must not fail. The NULL counts should be 0. If they aren't, show the user the affected rows and ask: a NULL expression gives a NULL hook (the row has no instance of the concept, e.g. a shut-down Sodir field without an operator has no company), which is accepted only if they agree; never substitute a placeholder value (`coalesce(x, 0)`), which would join every such row to one fake instance. Both NULL counts must then be equal (the two expressions NULL on the same rows). The three distinct counts (a NULL pair counts as one in the third) should be equal (one development value per production value); if not, tell the user: the two modes would then group rows differently. If the std view doesn't exist yet (new dataset), check the expressions against the Std script's columns (or a downloaded file) and run the query once data is loaded.

Datasets of the same source share `key_set` for a given concept (`no_sodir.sup.field` for every Sodir dataset). That's intended: it's how their rows meet on the hook. Mention it if the user expects one key set per dataset. Their expressions must give the same values for the same business key in every dataset (same id, same spelling of the name), or their hooks won't meet.

## 3. Write

- New business concept: append `<next id>,<code>,<name>,<description>,<business_domain_id>` to `data/static/business_concepts.csv` (quote fields containing commas). Never change the `business_domain_id` of an existing concept.
- Append `<next id>,<business_concept_id>,<dataset_id>,<hook_expression_dev>,<hook_expression_prod>,<hook_encoding>,<hook_role>` (role empty if none) to `data/static/hooks.csv`. Quote an expression if it contains a comma or a quote (`"concat_ws('-', a, b)"`).

Keep the existing rows and their order; ids are never reused or renumbered.

## 4. Verify

1. `pytest tests/test_hook_static.py` (in the app container: `docker compose run --rm --no-deps app sh -c "pip install -q pytest && python -m pytest -q tests/test_hook_static.py"`, from `architecture/docker`). It builds the hooks from the real CSVs.
2. On the Docker stack: `docker compose restart duckdb`, then `docker compose logs duckdb --since 1m | grep -i error` must show nothing about hooks (a bad row fails the build and keeps the previous table).
3. Check the derived identifiers:
   ```bash
   docker compose run --rm app python -c "from storage import duck; print(duck.query('SELECT id, hook_expression_dev, hook_expression_prod, hook_encoding, hook_role, key_set, hex(key_set_binary), hook_column FROM hook.metadata.hooks ORDER BY id')[1])"
   ```
   The new row must show its expressions and encoding, `<source code>.<domain code>.<concept code>` and `<source id><domain id><concept id>`, each as 2 hex digits.

## Report

Tell the user the new hook's `id`, expressions, encoding, role, `key_set`, `key_set_binary` and `hook_column`, and any business concept added (with its domain). The dataset's frame views don't pick the hook up by themselves (they are static SQL): if the dataset has frames (`sql/ddl/library/<code>[_dev].sql`), offer to update them with the `add-frame` skill; otherwise offer to create them.
