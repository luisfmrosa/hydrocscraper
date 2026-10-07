---
name: add-business-domain
description: Add a business domain to hydrocscraper — a group of business concepts (e.g. Supply; elsewhere Finance, HR, Sales) in data/static/business_domains.csv, whose code and id become part of every hook key set of its concepts. Use when the user asks to add, define or register a business domain, or when a new business concept needs a domain that doesn't exist yet.
---

# Add a business domain

A business domain groups business concepts. Every business concept belongs to exactly one domain (`business_concepts.csv` `business_domain_id`), and the domain is part of every hook of its concepts:
- `key_set` = `<source code>.<business domain code>.<business concept code>`, e.g. `no_sodir.sup.field`;
- `key_set_binary` = source id || business domain id || business concept id, one byte each, e.g. `0x080101`.

`data/static/business_domains.csv` holds:

| Column | Content |
|---|---|
| `id` | Integer, the next one (max existing `id` + 1); **≤ 255** (one byte of `key_set_binary`) |
| `code` | Exactly **3 lowercase letters or digits** (`sup`), unique: it becomes part of `key_set`, lowercase like source and concept codes |
| `name` | Free text, not empty (`Supply`) |
| `description` | Free text: what the domain groups |

`sql/ddl/45_hook_static.sql` rebuilds `hook.metadata.business_domains` from it at each server start and fails (keeping the previous table, error in the server log) on a duplicate `id` or `code`, a code that isn't 3 lowercase letters or digits, an empty name or an id above 255.

## 1. Ask for the input

Ask the user, unless already given: the domain's **name** and **description**, and its **code** (suggest one: the first three letters of the name in lowercase, e.g. Supply → `sup`, Demand → `dem`, Finance → `fin`, unless taken). Show the existing rows of `data/static/business_domains.csv` so they can check it's really new.

## 2. Check before writing

Stop and tell the user if any of these fails:
- the code matches `^[a-z0-9]{3}$` and isn't already in the file;
- the name isn't empty and no existing domain means the same thing (a near-duplicate splits concepts that belong together);
- the next `id` is ≤ 255; if it would be 256, raise it with the user (the binary format would have to change).

A domain is final once a concept of it has a hook: its `id` and `code` are inside those hooks, so changing either changes every hook of every concept in it. Ids are never reused or renumbered. Name and description can be edited freely.

## 3. Write

Append `<next id>,<code>,<name>,<description>` to `data/static/business_domains.csv` (quote fields containing commas). Keep the existing rows and their order.

A domain is useful only through its concepts: if the user is adding one for a new concept, continue with the `add-hook` skill (which adds the concept with `business_domain_id` = the new id). An existing concept is never moved to the new domain: create a new concept instead.

## 4. Verify

1. `pytest tests/test_hook_static.py` (in the app container: `docker compose run --rm --no-deps app sh -c "pip install -q pytest && python -m pytest -q tests/test_hook_static.py"`, from `architecture/docker`). It builds the metadata from the real CSVs.
2. On the Docker stack: `docker compose restart duckdb`, then `docker compose logs duckdb --since 1m | grep -i error` must show nothing about `business_domains`.
3. Check the table:
   ```bash
   docker compose run --rm --no-deps app python -c "from storage import duck; print(duck.query('SELECT * FROM hook.metadata.business_domains ORDER BY id')[1])"
   ```

## Report

Tell the user the new domain's `id`, `code`, `name`, the `key_set` and `key_set_binary` prefixes its concepts' hooks will have (`<source code>.<code>.…`, `<source id><id as 2 hex digits>…`), and offer the `add-hook` skill to add concepts and hooks to it.
