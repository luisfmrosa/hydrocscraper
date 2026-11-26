{#- Library views over one Lake table, built from the Hook metadata
    (hook.metadata.hooks and .datasets, rebuilt from data/static/*.csv by
    sql/ddl/45_hook_static.sql at every server start).

    hook_frame(source, table, mode): SCD2 frame, one version per Lake row:
      hook columns   one per hook of the dataset <source>_<table>, in hook id
                     order, named by hook_column; the key sets are written into
                     the view as literals:
                       dev   VARCHAR  '<key_set>|' || (hook_expression_dev)::VARCHAR
                       prod  BLOB     key_set_binary || hook_expression_prod
                                      encoded per hook_encoding (unsigned,
                                      big-endian; a negative or too large
                                      value fails the cast, so the view fails
                                      instead of building a wrong hook):
                         integer  unhex(printf('%08x', (expr)::UINTEGER))
                         bigint   unhex(printf('%016x', (expr)::UBIGINT))
                         varchar  encode((expr)::VARCHAR)
      data columns   the Lake table's, then its lineage (___Lake_md5,
                     ___Lake_datasource, ___Lake_sourcefile)
      ___Effective_From  when the version was observed (___Lake_load_timestamp)
      ___Effective_To    when the key's next version was observed; 'infinity'
                         for its last one (no time zone: query open versions
                         with ___Effective_To = 'infinity'::TIMESTAMPTZ)
      ___Is_Deleted      ___Lake_isdeleted: the key disappeared at
                         ___Effective_From
    The key is the dataset's `keys` (datasets.csv). A dataset without hooks
    fails: a frame exists to carry hooks.

    hook_latest(frame): the frame's current, non-deleted versions, without the
    three SCD2 columns. -#}

{% macro hook_frame(source_name, table, mode) %}
  {%- if mode not in ['dev', 'prod'] -%}
    {{ exceptions.raise_compiler_error("hook_frame: mode must be 'dev' or 'prod', not " ~ mode) }}
  {%- endif -%}
  {%- set lake = source(source_name, table) -%}
  {%- set code = source_name ~ '_' ~ table -%}
  {%- if not execute -%}
    {{ return('SELECT 1 FROM ' ~ lake) }}
  {%- endif -%}

  {%- set dataset = run_query(
      "SELECT id, keys FROM hook.metadata.datasets WHERE code = '" ~ code ~ "'") -%}
  {%- if dataset.rows | length != 1 -%}
    {{ exceptions.raise_compiler_error("hook_frame: dataset " ~ code ~ " not found in hook.metadata.datasets") }}
  {%- endif -%}
  {%- set keys = [] -%}
  {%- for key in (dataset.rows[0][1] or '').split(',') if key.strip() -%}
    {%- do keys.append(key.strip()) -%}
  {%- endfor -%}
  {%- if not keys -%}
    {{ exceptions.raise_compiler_error("hook_frame: dataset " ~ code ~ " has no keys in datasets.csv") }}
  {%- endif -%}

  {%- set hooks = run_query(
      "SELECT hook_column, key_set, hex(key_set_binary), hook_expression_dev, hook_expression_prod, hook_encoding"
      ~ " FROM hook.metadata.hooks WHERE dataset_id = " ~ dataset.rows[0][0] ~ " ORDER BY id") -%}
  {%- if hooks.rows | length == 0 -%}
    {{ exceptions.raise_compiler_error("hook_frame: dataset " ~ code ~ " has no hooks in hooks.csv") }}
  {%- endif %}
SELECT
{%- for h in hooks.rows %}
  {%- if mode == 'dev' %}
    '{{ h[1] }}' || '|' || ({{ h[3] }})::VARCHAR AS {{ h[0] }},
  {%- elif h[5] == 'integer' %}
    unhex('{{ h[2] }}') || unhex(printf('%08x', ({{ h[4] }})::UINTEGER)) AS {{ h[0] }},
  {%- elif h[5] == 'bigint' %}
    unhex('{{ h[2] }}') || unhex(printf('%016x', ({{ h[4] }})::UBIGINT)) AS {{ h[0] }},
  {%- elif h[5] == 'varchar' %}
    unhex('{{ h[2] }}') || encode(({{ h[4] }})::VARCHAR) AS {{ h[0] }},
  {%- else %}
    {{ exceptions.raise_compiler_error("hook_frame: unknown hook_encoding " ~ h[5] ~ " for " ~ h[0]) }}
  {%- endif %}
{%- endfor %}
    * EXCLUDE (___Lake_load_timestamp, ___Lake_isdeleted),
    ___Lake_load_timestamp AS ___Effective_From,
    lead(___Lake_load_timestamp, 1, 'infinity'::TIMESTAMPTZ) OVER (
        PARTITION BY {{ keys | join(', ') }}
        ORDER BY ___Lake_load_timestamp
    ) AS ___Effective_To,
    ___Lake_isdeleted AS ___Is_Deleted
FROM {{ lake }}
{% endmacro %}

{% macro hook_latest(frame) %}
SELECT * EXCLUDE (___Effective_From, ___Effective_To, ___Is_Deleted)
FROM {{ frame }}
WHERE ___Effective_To = 'infinity'::TIMESTAMPTZ
  AND NOT ___Is_Deleted
{% endmacro %}
