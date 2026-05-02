{#
  format_metrics(metrics)
  -----------------------
  Renders a list of metric dicts as comma-separated aggregation expressions:

      [{name: total, based_on: amount, operation: sum}]
      → "sum(amount) as total"

  Operation mapping:
      count            → count(<col>)
      count_distinct   → count(distinct <col>)
      sum / avg / min / max → <op>(<col>)
#}

{% macro format_metrics(metrics) %}
    {%- if not metrics or (metrics | length) == 0 -%}
        {%- do return("") -%}
    {%- endif -%}

    {%- set parts = [] -%}
    {%- for m in metrics -%}
        {%- do parts.append(dbt_forge.forge_format_one_metric(m)) -%}
    {%- endfor -%}

    {{- parts | join(',\n    ') -}}
{% endmacro %}


{% macro forge_format_one_metric(m) %}
    {%- set op = m.operation -%}
    {%- set col = m.based_on -%}
    {%- set name = m.name -%}

    {%- if op == 'count_distinct' -%}
        count(distinct {{ col }}) as {{ name }}
    {%- else -%}
        {{ op }}({{ col }}) as {{ name }}
    {%- endif -%}
{% endmacro %}
