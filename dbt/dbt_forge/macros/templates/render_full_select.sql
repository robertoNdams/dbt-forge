{#
  render_full_select(model_cfg)
  -----------------------------
  The default template: the full pipeline, top to bottom.

  Composition (per the manifest):
      full_select
        → thresholds_select         (only if metrics)
            → aggregation_select
        → sorted_select wraps either thresholds (if metrics) or filtered:
              filtered_select
                → distinct_select?
                    → base_select

  Implementation: full_select == sorted_select. We keep the name because users
  describe their *intent* (a full materialized SELECT) — and because keeping a
  distinct top-level entry point makes future override-by-name straightforward.
#}

{% macro render_full_select(model_cfg) %}
    {{- adapter.dispatch('render_full_select', 'dbt_forge')(model_cfg) -}}
{% endmacro %}


{% macro default__render_full_select(model_cfg) %}
    {{- dbt_forge.render_sorted_select(model_cfg) -}}
{% endmacro %}
