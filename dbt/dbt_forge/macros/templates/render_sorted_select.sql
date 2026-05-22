{#
  render_sorted_select(model_cfg)
  -------------------------------
  Wraps the appropriate inner template with ORDER BY.

  Inner choice:
      - if metrics:    thresholds_select (covers aggregation + having)
      - else:          filtered_select   (covers base/distinct + where)

  This is what makes `template: full_select` work for both aggregated and
  non-aggregated models with a single declarative config.
#}

{% macro render_sorted_select(model_cfg) %}
    {{- adapter.dispatch('render_sorted_select', 'dbt_forge')(model_cfg) -}}
{% endmacro %}


{% macro default__render_sorted_select(model_cfg) %}
    {%- if (model_cfg.get('metrics', []) | length) > 0 -%}
        {%- set inner = dbt_forge.render_thresholds_select(model_cfg) -%}
    {%- else -%}
        {%- set inner = dbt_forge.render_filtered_select(model_cfg) -%}
    {%- endif -%}

    {%- set sort_items = model_cfg.get('sort_by', []) -%}

    {%- if (sort_items | length) == 0 -%}
        {{- inner -}}
    {%- else -%}
        {%- set order_body = dbt_forge.format_sort(sort_items) -%}
{{ inner }}
order by
    {{ order_body }}
    {%- endif -%}
{% endmacro %}
