{#
  render_base_select(model_cfg)
  -----------------------------
  The atom of the composition chain.

  Produces:
      select
          <columns>
      from <ref|source>

  All other templates wrap this one (directly or transitively).
#}

{% macro render_base_select(model_cfg) %}
    {{- adapter.dispatch('default__render_base_select', 'dbt_forge')(model_cfg) -}}
{% endmacro %}


{% macro default__render_base_select(model_cfg) %}
    {%- set cols = dbt_forge.format_columns(model_cfg.get('select_columns', ['*'])) -%}
    {%- set src = dbt_forge.resolve_source(model_cfg) -%}
select
    {{ cols }}
from {{ src }}
{%- endmacro %}
