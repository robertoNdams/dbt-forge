{#
  dispatch_template(template_name, model_cfg)
  -------------------------------------------
  Dispatches dynamically to a render_<template_name> macro, but via a
  cascade of literal-string `adapter.dispatch(...)` calls.

  WHY THIS EXISTS
  ---------------
  dbt statically inspects every `adapter.dispatch(...)` call at parse time
  to build the macro dependency graph (see dbt.clients.jinja_static.
  statically_parse_adapter_dispatch). The static parser expects the first
  argument to be a string literal — passing a runtime expression like
  `'render_' ~ template_name` raises:

      AttributeError: 'Concat' object has no attribute 'value'

  during `dbt parse`. We work around this by switching on the known set of
  templates and dispatching to each one by its literal name. Adding a new
  template means extending this macro.

  Raises a compiler error for unknown templates so typos in YAML configs
  surface as a clear message rather than a silent fallthrough.
#}

{% macro dispatch_template(template_name, model_cfg) %}
    {%- if template_name == 'base_select' -%}
        {{- adapter.dispatch('render_base_select', 'dbt_forge')(model_cfg) -}}
    {%- elif template_name == 'distinct_select' -%}
        {{- adapter.dispatch('render_distinct_select', 'dbt_forge')(model_cfg) -}}
    {%- elif template_name == 'filtered_select' -%}
        {{- adapter.dispatch('render_filtered_select', 'dbt_forge')(model_cfg) -}}
    {%- elif template_name == 'aggregation_select' -%}
        {{- adapter.dispatch('render_aggregation_select', 'dbt_forge')(model_cfg) -}}
    {%- elif template_name == 'thresholds_select' -%}
        {{- adapter.dispatch('render_thresholds_select', 'dbt_forge')(model_cfg) -}}
    {%- elif template_name == 'sorted_select' -%}
        {{- adapter.dispatch('render_sorted_select', 'dbt_forge')(model_cfg) -}}
    {%- elif template_name == 'full_select' -%}
        {{- adapter.dispatch('render_full_select', 'dbt_forge')(model_cfg) -}}
    {%- elif template_name == 'ctes_select' -%}
        {{- adapter.dispatch('render_ctes_select', 'dbt_forge')(model_cfg) -}}
    {%- else -%}
        {{ exceptions.raise_compiler_error(
            "Unknown template '" ~ template_name ~ "'. Known templates: "
            "base_select, distinct_select, filtered_select, aggregation_select, "
            "thresholds_select, sorted_select, full_select, ctes_select. "
            "To register a new template, extend the dispatch_template macro."
        ) }}
    {%- endif -%}
{% endmacro %}
