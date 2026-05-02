{#
  render_ctes_select(model_cfg)
  -----------------------------
  Wraps the chosen inner template with CTEs declared via `include_sources`.

  Each entry in include_sources becomes a CTE. The final select clause is
  produced by dispatching to render_<template> on the parent model_cfg, but
  with `include_sources` stripped (otherwise we'd recurse infinitely).

  Output shape:

      with
      <name1> as (
          <inner sql>
      ),
      <name2> as (
          <inner sql>
      )
      <main select>

  Each include_source dict is itself a (smaller) model_cfg: it has
  `source` / `source_model`, optional `template`, `select_columns`, `filters`.
  We dispatch to its template just like a normal model — composition all the
  way down.
#}

{% macro render_ctes_select(model_cfg) %}
    {{- adapter.dispatch('default__render_ctes_select', 'dbt_forge')(model_cfg) -}}
{% endmacro %}


{% macro default__render_ctes_select(model_cfg) %}
    {%- set includes = model_cfg.get('include_sources', []) -%}
    {%- if (includes | length) == 0 -%}
        {{ exceptions.raise_compiler_error(
            "render_ctes_select called on '" ~ model_cfg.name ~ "' but include_sources is empty."
        ) }}
    {%- endif -%}

    {#- Render each CTE -#}
    {%- set cte_blocks = [] -%}
    {%- for inc in includes -%}
        {%- set inc_template = inc.get('template', 'base_select') -%}
        {%- set inc_sql = adapter.dispatch('render_' ~ inc_template, 'dbt_forge')(inc) -%}
        {%- set block = inc.name ~ ' as (\n    ' ~ (inc_sql | trim | replace('\n', '\n    ')) ~ '\n)' -%}
        {%- do cte_blocks.append(block) -%}
    {%- endfor -%}

    {#- Render the main select. We rebuild the cfg without include_sources to
        avoid an infinite loop, and inject `_local_ctes` so that resolve_source
        emits bare identifiers when source_model matches a CTE name. -#}
    {%- set parent_template = model_cfg.get('template', 'full_select') -%}
    {%- set cte_names = [] -%}
    {%- for inc in includes -%}{%- do cte_names.append(inc.name) -%}{%- endfor -%}

    {%- set inner_cfg = {} -%}
    {%- for k, v in model_cfg.items() -%}
        {%- if k != 'include_sources' -%}
            {%- do inner_cfg.update({k: v}) -%}
        {%- endif -%}
    {%- endfor -%}
    {%- do inner_cfg.update({'_local_ctes': cte_names}) -%}
    {%- set main_sql = adapter.dispatch('render_' ~ parent_template, 'dbt_forge')(inner_cfg) -%}

with
{{ cte_blocks | join(',\n') }}

{{ main_sql }}
{%- endmacro %}
