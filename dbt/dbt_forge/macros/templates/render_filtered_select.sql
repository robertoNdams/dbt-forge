{#
  render_filtered_select(model_cfg)
  ---------------------------------
  Wraps render_base_select (or render_distinct_select if model_cfg.distinct
  is true) with a WHERE clause built from `filters`.

  Composition: filtered → distinct? → base.
#}

{% macro render_filtered_select(model_cfg) %}
    {{- adapter.dispatch('default__render_filtered_select', 'dbt_forge')(model_cfg) -}}
{% endmacro %}


{% macro default__render_filtered_select(model_cfg) %}
    {%- if model_cfg.get('distinct') -%}
        {%- set inner = dbt_forge.render_distinct_select(model_cfg) -%}
    {%- else -%}
        {%- set inner = dbt_forge.render_base_select(model_cfg) -%}
    {%- endif -%}

    {%- set filters = model_cfg.get('filters', []) -%}
    {%- if (filters | length) == 0 -%}
        {{- inner -}}
    {%- else -%}
        {%- set where_body = dbt_forge.format_filters(filters) -%}
{{ inner }}
where {{ where_body }}
    {%- endif -%}
{% endmacro %}
