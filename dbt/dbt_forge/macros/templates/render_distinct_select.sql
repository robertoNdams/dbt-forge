{#
  render_distinct_select(model_cfg)
  ---------------------------------
  Adds the DISTINCT keyword to the SELECT produced by render_base_select.

  Composition: distinct → base.

  Activated either by `template: distinct_select` or by `distinct: true` in
  any template that defers to this one (filtered_select does so).
#}

{% macro render_distinct_select(model_cfg) %}
    {{- adapter.dispatch('default__render_distinct_select', 'dbt_forge')(model_cfg) -}}
{% endmacro %}


{% macro default__render_distinct_select(model_cfg) %}
    {%- set base = dbt_forge.render_base_select(model_cfg) -%}
    {#- Surgical replace: turn "select\n" into "select distinct\n" once. -#}
    {{- base | replace('select\n', 'select distinct\n', 1) -}}
{% endmacro %}
