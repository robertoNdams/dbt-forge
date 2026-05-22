{#
  emit_file(path, content)
  ------------------------
  Emits a content block to stdout wrapped in delimiters that the CLI can parse:

    <<<DBT_FORGE_FILE path="models/generated/foo.sql">>>
    ...content...
    <<<DBT_FORGE_END>>>

  We use `print()` rather than `log()` because:
    - `log()` adds a timestamp prefix that would corrupt the captured content;
    - `print()` writes raw text to stdout (dbt 1.7+).

  The path is single-quoted with backslash escaping if it ever contains quotes
  (it shouldn't — output_dir + model name).
#}

{% macro emit_file(path, content) %}
    {%- set safe_path = path | replace('"', '\\"') -%}
    {%- do print('<<<DBT_FORGE_FILE path="' ~ safe_path ~ '">>>') -%}
    {%- do print(content) -%}
    {%- do print('<<<DBT_FORGE_END>>>') -%}
{% endmacro %}


{#
  emit_dry_run(path, content)
  ---------------------------
  Same protocol but with a different open delimiter so the CLI knows not to write.
#}

{% macro emit_dry_run(path, content) %}
    {%- set safe_path = path | replace('"', '\\"') -%}
    {%- do print('<<<DBT_FORGE_DRYRUN path="' ~ safe_path ~ '">>>') -%}
    {%- do print(content) -%}
    {%- do print('<<<DBT_FORGE_END>>>') -%}
{% endmacro %}
