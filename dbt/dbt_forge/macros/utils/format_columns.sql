{#
  format_columns(columns)
  -----------------------
  Renders a list of column names as a comma-separated, indented SELECT body.

  Examples:
      ['*']                       → "*"
      ['id', 'name']              → "id,\n    name"
      ['id', 'name AS full_name'] → "id,\n    name AS full_name"

  Whitespace expectations: the caller places this output directly after
  "select " (or "select distinct "). No leading newline.
#}

{% macro format_columns(columns) %}
    {%- if not columns or (columns | length) == 0 -%}
        *
    {%- elif (columns | length) == 1 -%}
        {{ columns[0] }}
    {%- else -%}
        {%- for c in columns -%}
            {{ c }}{% if not loop.last %},{{ '\n    ' }}{% endif %}
        {%- endfor -%}
    {%- endif -%}
{% endmacro %}
