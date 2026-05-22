{#
  build_schema_yml(models)
  ------------------------
  Returns a string with the YAML content for the generated schema.yml.

  Format:
      version: 2

      models:
        - name: <model_name>
          description: "<description>"
          columns:
            - name: <col>
              description: "<col description>"
              tests:
                - <test1>
                - <test2>

  We build the YAML manually rather than using a Python serializer (no
  modules.yaml in dbt's sandbox) — but the structure is rigid enough that
  this is straightforward.
#}

{% macro build_schema_yml(models) %}
    {%- set lines = [] -%}
    {%- do lines.append('version: 2') -%}
    {%- do lines.append('') -%}
    {%- do lines.append('models:') -%}

    {%- for m in models -%}
        {%- do lines.append('  - name: ' ~ m.name) -%}

        {%- if m.get('description') -%}
            {%- do lines.append('    description: ' ~ dbt_forge.forge_yaml_escape(m.description)) -%}
        {%- endif -%}

        {%- set columns_meta = m.get('columns_meta', []) -%}
        {%- if (columns_meta | length) > 0 -%}
            {%- do lines.append('    columns:') -%}
            {%- for col in columns_meta -%}
                {%- do lines.append('      - name: ' ~ col.name) -%}
                {%- if col.get('description') -%}
                    {%- do lines.append('        description: ' ~ dbt_forge.forge_yaml_escape(col.description)) -%}
                {%- endif -%}
                {%- set tests = col.get('tests', []) -%}
                {%- if (tests | length) > 0 -%}
                    {%- do lines.append('        tests:') -%}
                    {%- for t in tests -%}
                        {%- do lines.append('          - ' ~ t) -%}
                    {%- endfor -%}
                {%- endif -%}
            {%- endfor -%}
        {%- endif -%}

        {%- do lines.append('') -%}
    {%- endfor -%}

    {{- lines | join('\n') -}}
{% endmacro %}


{#
  Minimal YAML scalar quoting: wrap strings containing special chars in
  double quotes with escaped quotes / backslashes. Plain identifiers and
  short ASCII descriptions remain unquoted.
#}

{% macro forge_yaml_escape(s) %}
    {%- if s is none -%}
        ""
    {%- else -%}
        {%- set txt = s | string -%}
        {%- if txt | length == 0 -%}
            ""
        {%- elif (':' in txt) or ('#' in txt) or ('"' in txt) or ('\n' in txt) or txt.startswith('-') or txt.startswith('?') or txt.startswith('&') or txt.startswith('*') or txt.startswith('!') or txt.startswith('|') or txt.startswith('>') or txt.startswith('%') or txt.startswith('@') -%}
            "{{- txt | replace('\\', '\\\\') | replace('"', '\\"') | replace('\n', '\\n') -}}"
        {%- else -%}
            {{- txt -}}
        {%- endif -%}
    {%- endif -%}
{% endmacro %}
