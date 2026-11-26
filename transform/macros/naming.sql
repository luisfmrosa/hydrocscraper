{#- Library models are named frame_<code>[_dev] and latest_<code>[_dev] (model
    names are unique in a dbt project, and both views share <code>); the prefix
    gives the schema, the rest the view name: library.frame.<code>[_dev].
    Other models keep dbt's defaults, without the target schema prefix. -#}

{% macro library_parts(node) -%}
  {%- for schema in ['frame', 'latest'] -%}
    {%- if node.name.startswith(schema ~ '_') and node.fqn[1] == 'library' -%}
      {{ return([schema, node.name[schema | length + 1:]]) }}
    {%- endif -%}
  {%- endfor -%}
  {{ return(none) }}
{%- endmacro %}

{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- set parts = library_parts(node) -%}
  {%- if parts -%}{{ parts[0] }}
  {%- elif custom_schema_name -%}{{ custom_schema_name | trim }}
  {%- else -%}{{ target.schema }}
  {%- endif -%}
{%- endmacro %}

{% macro generate_alias_name(custom_alias_name, node) -%}
  {%- set parts = library_parts(node) -%}
  {%- if custom_alias_name -%}{{ custom_alias_name | trim }}
  {%- elif parts -%}{{ parts[1] }}
  {%- else -%}{{ node.name }}
  {%- endif -%}
{%- endmacro %}
