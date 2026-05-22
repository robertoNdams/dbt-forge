{#
  format_filters(filters)
  -----------------------
  Renders a list of filter dicts as a SQL boolean expression suitable for
  WHERE or HAVING. Returns "" if the list is empty (caller decides whether
  to emit the WHERE keyword).

  A filter dict looks like:
      { column: <str>, op: <Operator>, value: <scalar | list | None> }

  Operator → SQL mapping:
      "=" "!=" ">" ">=" "<" "<=" "like"  → infix
      "in" / "not in"                    → "x IN (a, b, c)"
      "is null" / "is not null"          → unary

  Quoting rule: strings are single-quoted with `'` escaped to `''`. Numbers
  and bools are rendered literally. None becomes NULL.
#}

{% macro format_filters(filters) %}
    {%- if not filters or (filters | length) == 0 -%}
        {%- do return("") -%}
    {%- endif -%}

    {%- set parts = [] -%}
    {%- for f in filters -%}
        {%- do parts.append(dbt_forge.forge_format_one_filter(f)) -%}
    {%- endfor -%}

    {{- parts | join('\n  and ') -}}
{% endmacro %}


{% macro forge_format_one_filter(f) %}
    {%- set col = f.get('column') or f.get('metric') -%}
    {%- set op = f.get('op') -%}
    {%- set val = f.get('value') -%}

    {%- if op in ('is null', 'is not null') -%}
        {{- col }} {{ op }}
    {%- elif op in ('in', 'not in') -%}
        {%- set rendered_items = [] -%}
        {%- for v in val -%}
            {%- do rendered_items.append(dbt_forge.forge_lit(v)) -%}
        {%- endfor -%}
        {{- col }} {{ op }} ({{ rendered_items | join(', ') }})
    {%- else -%}
        {{- col }} {{ op }} {{ dbt_forge.forge_lit(val) }}
    {%- endif -%}
{% endmacro %}


{% macro forge_lit(v) %}
    {%- if v is none -%}
        null
    {%- elif v is sameas true -%}
        true
    {%- elif v is sameas false -%}
        false
    {%- elif v is number -%}
        {{- v -}}
    {%- else -%}
        '{{- v | replace("'", "''") -}}'
    {%- endif -%}
{% endmacro %}
