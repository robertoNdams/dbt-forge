{#
  render_aggregation_select(model_cfg)
  ------------------------------------
  Builds an aggregation query:

      select
          <breakdown_by>,
          <metrics>
      from <ref|source>
      [where <filters>]
      group by <breakdown_by>

  This template is structurally different from base (it injects the metrics
  into the SELECT list and adds GROUP BY), so it is a peer of `filtered_select`
  rather than a wrapper of it. We keep the dispatch chain consistent: a model
  using `template: aggregation_select` (or `template: thresholds_select`)
  goes through this macro, then optionally through thresholds.

  Composition: aggregation → (resolves to: select + where + group by)
#}

{% macro render_aggregation_select(model_cfg) %}
    {{- adapter.dispatch('render_aggregation_select', 'dbt_forge')(model_cfg) -}}
{% endmacro %}


{% macro default__render_aggregation_select(model_cfg) %}
    {%- set breakdown = model_cfg.get('breakdown_by', []) -%}
    {%- set metrics = model_cfg.get('metrics', []) -%}
    {%- set filters = model_cfg.get('filters', []) -%}
    {%- set src = dbt_forge.resolve_source(model_cfg) -%}

    {%- if (metrics | length) == 0 -%}
        {{ exceptions.raise_compiler_error(
            "Model '" ~ model_cfg.name ~ "' uses an aggregation template but has no `metrics`."
        ) }}
    {%- endif -%}

    {%- set select_parts = [] -%}
    {%- for c in breakdown -%}
        {%- do select_parts.append(c) -%}
    {%- endfor -%}
    {%- set metric_lines = dbt_forge.format_metrics(metrics) -%}
    {%- if metric_lines -%}
        {%- do select_parts.append(metric_lines) -%}
    {%- endif -%}

select
    {{ select_parts | join(',\n    ') }}
from {{ src }}
    {%- if (filters | length) > 0 %}
where {{ dbt_forge.format_filters(filters) }}
    {%- endif %}
    {%- if (breakdown | length) > 0 %}
group by {{ breakdown | join(', ') }}
    {%- endif -%}
{% endmacro %}
