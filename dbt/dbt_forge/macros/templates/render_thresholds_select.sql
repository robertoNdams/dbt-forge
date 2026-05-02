{#
  render_thresholds_select(model_cfg)
  -----------------------------------
  Wraps render_aggregation_select with a HAVING clause built from `thresholds`.

  Composition: thresholds → aggregation → (filters + group by).

  Note: `thresholds` are validated upstream (Pydantic) to reference only
  declared metrics — see ModelConfig._thresholds_reference_known_metrics.
#}

{% macro render_thresholds_select(model_cfg) %}
    {{- adapter.dispatch('default__render_thresholds_select', 'dbt_forge')(model_cfg) -}}
{% endmacro %}


{% macro default__render_thresholds_select(model_cfg) %}
    {%- set inner = dbt_forge.render_aggregation_select(model_cfg) -%}
    {%- set thresholds = model_cfg.get('thresholds', []) -%}

    {%- if (thresholds | length) == 0 -%}
        {{- inner -}}
    {%- else -%}
        {#- Reuse format_filters: thresholds have the same {column/metric, op, value} shape. -#}
        {%- set having_body = dbt_forge.format_filters(thresholds) -%}
{{ inner }}
having {{ having_body }}
    {%- endif -%}
{% endmacro %}
