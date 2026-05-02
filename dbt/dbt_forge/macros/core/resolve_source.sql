{#
  resolve_source(model_cfg)
  -------------------------
  Returns a string containing a dbt Jinja expression that will resolve
  to the underlying relation:

    - `source_model` → "{{ ref('<name>') }}"
    - `source`       → "{{ source('<schema>', '<table>') }}"

  We emit the *literal text* of the ref/source call so that the generated
  .sql files contain proper dbt references and participate in the DAG.

  Raises a compiler error if neither / both are set.
#}

{% macro resolve_source(model_cfg) %}
    {%- set source_model = model_cfg.get('source_model') -%}
    {%- set source = model_cfg.get('source') -%}
    {%- set local_ctes = model_cfg.get('_local_ctes', []) -%}

    {%- if source_model and source -%}
        {{ exceptions.raise_compiler_error(
            "Model '" ~ model_cfg.name ~ "': specify exactly one of "
            "`source` or `source_model`, not both."
        ) }}
    {%- elif source_model -%}
        {#- If source_model matches a CTE name declared by an enclosing
            render_ctes_select, emit the bare identifier instead of ref(). -#}
        {%- if source_model in local_ctes -%}
            {{- source_model -}}
        {%- else -%}
            {{- "{{ ref('" ~ source_model ~ "') }}" -}}
        {%- endif -%}
    {%- elif source -%}
        {%- set parts = source.split('.') -%}
        {%- if parts | length != 2 -%}
            {{ exceptions.raise_compiler_error(
                "Model '" ~ model_cfg.name ~ "': `source` must be 'schema.table' (got '" ~ source ~ "')."
            ) }}
        {%- endif -%}
        {{- "{{ source('" ~ parts[0] ~ "', '" ~ parts[1] ~ "') }}" -}}
    {%- else -%}
        {{ exceptions.raise_compiler_error(
            "Model '" ~ model_cfg.name ~ "': must define either `source` or `source_model`."
        ) }}
    {%- endif -%}
{% endmacro %}
