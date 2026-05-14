{#
  generate_model(config, options)
  -------------------------------
  Entrypoint macro. Called by `dbt run-operation generate_model --args '<json>'`.

  Architecture note: dbt's Jinja sandbox restricts `modules` to
  {datetime, pytz, re, itertools} — `os` and `io` are unavailable. Macros
  therefore CANNOT write files directly. Instead this macro renders each
  artifact and emits it to stdout wrapped in a delimiter:

    <<<DBT_FORGE_FILE path="models/generated/foo.sql">>>
    ...rendered content...
    <<<DBT_FORGE_END>>>

  The CLI captures dbt's stdout, parses these blocks, and writes files.
  This keeps macros pure (no IO, just rendering) and the CLI orchestrates.
#}

{% macro generate_model(config=none, options=none) %}
    {%- if config is none or options is none -%}
        {{ exceptions.raise_compiler_error(
            "generate_model requires `config` and `options` keyword arguments. "
            "Are you invoking via the dbt-forge CLI?"
        ) }}
    {%- endif -%}

    {%- set output_dir = options.get('output_dir') -%}
    {%- set dry_run = options.get('dry_run', false) -%}

    {%- if not output_dir -%}
        {{ exceptions.raise_compiler_error("`options.output_dir` is required.") }}
    {%- endif -%}

    {%- set models = config.get('models', []) -%}
    {%- if (models | length) == 0 -%}
        {{ log("dbt-forge: no models in config — nothing to do.", info=true) }}
        {%- do return(none) -%}
    {%- endif -%}

    {{ log("dbt-forge: rendering " ~ (models | length) ~ " models", info=true) }}

    {%- for model_cfg in models -%}
        {%- set template_name = model_cfg.get('template', 'full_select') -%}

        {#- include_sources implies CTE wrapping regardless of template name. -#}
        {%- if model_cfg.get('include_sources') and (model_cfg.get('include_sources', []) | length) > 0 -%}
            {%- set rendered = dbt_forge.render_ctes_select(model_cfg) -%}
        {%- else -%}
            {%- set rendered = dbt_forge.dispatch_template(template_name, model_cfg) -%}
        {%- endif -%}

        {%- set materialized = model_cfg.get('output_type', 'view') -%}
        {%- set header = "{{ config(materialized='" ~ materialized ~ "') }}" -%}
        {%- set body = header ~ "\n\n" ~ (rendered | trim) ~ "\n" -%}

        {%- set rel_path = output_dir ~ '/' ~ model_cfg.name ~ '.sql' -%}

        {%- if dry_run -%}
            {%- do dbt_forge.emit_dry_run(rel_path, body) -%}
        {%- else -%}
            {%- do dbt_forge.emit_file(rel_path, body) -%}
        {%- endif -%}
    {%- endfor -%}

    {%- set schema_yml = dbt_forge.build_schema_yml(models) -%}
    {%- set schema_path = output_dir ~ '/schema.yml' -%}
    {%- if dry_run -%}
        {%- do dbt_forge.emit_dry_run(schema_path, schema_yml) -%}
    {%- else -%}
        {%- do dbt_forge.emit_file(schema_path, schema_yml) -%}
    {%- endif -%}
{% endmacro %}
