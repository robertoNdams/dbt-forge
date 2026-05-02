{#
  format_sort(sort_items)
  -----------------------
  Renders a list of sort items as the body of an ORDER BY clause.

  A sort item is either:
      { metric: <name>, order: asc|desc }
      { column: <name>, order: asc|desc }

  Returns "" if empty (caller decides whether to emit "order by").
#}

{% macro format_sort(sort_items) %}
    {%- if not sort_items or (sort_items | length) == 0 -%}
        {%- do return("") -%}
    {%- endif -%}

    {%- set parts = [] -%}
    {%- for s in sort_items -%}
        {%- set key = s.get('metric') or s.get('column') -%}
        {%- set order = s.get('order', 'asc') -%}
        {%- do parts.append(key ~ ' ' ~ order) -%}
    {%- endfor -%}

    {{- parts | join(',\n    ') -}}
{% endmacro %}
