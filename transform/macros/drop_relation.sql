{#- Every catalog dbt writes to is a DuckLake on the quack server (library,
    later dwh), and DuckLake rejects DROP ... CASCADE ("Cascade Drop not
    supported in DuckLake"). dbt-duckdb only drops without CASCADE for catalogs
    it attached itself as DuckLakes; ours are attached by the server, so this
    project drops without CASCADE everywhere (dbt's view materialization drops
    the replaced view's backup on every run). tests/test_library_dbt.py builds
    every model twice on DuckLake. -#}
{% macro duckdb__drop_relation(relation) -%}
  {% call statement('drop_relation', auto_begin=False) -%}
    drop {{ relation.type }} if exists {{ relation }}
  {%- endcall %}
{% endmacro %}
