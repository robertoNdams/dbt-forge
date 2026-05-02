# Templates & Composition

Templates are pure macros named `render_<name>` in the `dbt_forge` namespace. They compose by calling each other through `adapter.dispatch`, never via `{% include %}` or string concatenation outside Jinja.

---

## The composition tree

```
full_select  ─── (default)
   │
   └── sorted_select         (adds ORDER BY)
         │
         ├─[has metrics]──── thresholds_select   (adds HAVING)
         │                          │
         │                          └── aggregation_select   (SELECT … GROUP BY)
         │
         └─[no metrics] ──── filtered_select     (adds WHERE)
                                    │
                                    ├─[distinct]── distinct_select
                                    │                  │
                                    │                  └── base_select
                                    │
                                    └─────────────── base_select

ctes_select   (envelope; auto-selected when include_sources is set)
   │
   ├── for each include_source:
   │      adapter.dispatch('render_<inner_template>', 'dbt_forge')(inc_cfg)
   │
   └── adapter.dispatch('render_<parent_template>', 'dbt_forge')(stripped_cfg)
```

`sorted_select` is the structural hinge: it picks **`thresholds_select` if `metrics` is non-empty, otherwise `filtered_select`**. That single branch is what lets `template: full_select` work for both flat staging models and aggregated marts.

---

## Why dispatch matters

Every template is split into a thin entry macro and a `default__` implementation:

```jinja
{% macro render_filtered_select(model_cfg) %}
    {{- adapter.dispatch('default__render_filtered_select', 'dbt_forge')(model_cfg) -}}
{% endmacro %}

{% macro default__render_filtered_select(model_cfg) %}
    …implementation…
{% endmacro %}
```

This pattern gives users two extension points (see [EXTENDING.md](EXTENDING.md)):

1. **Project override** — define `render_filtered_select` in your own `macros/` folder; dispatch resolves to it before the `dbt_forge.default__` implementation.
2. **Adapter dispatch** — define `<adapter>__render_filtered_select` (e.g. `snowflake__…`) and dispatch routes to it on that warehouse.

---

## Calling siblings

Inside the package, templates call siblings via the `dbt_forge` namespace:

```jinja
{%- set inner = dbt_forge.render_base_select(model_cfg) -%}
```

This goes through dispatch too, so an override of `render_base_select` propagates everywhere `render_base_select` is composed.

---

## Underscore-prefixed macros are private

dbt's Jinja module loader (and the standard Jinja2 module model) hides macros whose names begin with `_`. Internal helpers therefore use the `forge_` prefix instead — `forge_format_one_filter`, `forge_lit`, `forge_yaml_escape`. This is purely an export-visibility constraint, not a style choice.

---

## Whitespace control

Every macro uses `{%- … -%}` consistently to strip the whitespace introduced by the Jinja delimiters themselves. The actual SQL formatting comes from explicit `\n`, `\n    ` (four-space indent), and `,\n    ` separators inside `format_columns`, `format_filters`, `format_metrics`, and `format_sort`.

The trade-off: rendered SQL is deterministic and diff-friendly, but the macro source has more whitespace markers than visually clean Jinja. Worth it.

---

## CTE handling — the one subtle bit

`render_ctes_select` builds an inner cfg that drops `include_sources` (to avoid recursion) and **adds an internal `_local_ctes` list** containing every CTE name declared. `resolve_source` checks this list:

```jinja
{%- if source_model in local_ctes -%}
    {{- source_model -}}             {# bare identifier #}
{%- else -%}
    {{- "{{ ref('" ~ source_model ~ "') }}" -}}
{%- endif -%}
```

So a parent that says `source_model: paid_orders` reads from the CTE rather than chasing a non-existent dbt model called `paid_orders`. CTE-internal references continue to use `ref()`/`source()` because `_local_ctes` is only injected at the outermost (parent) level.

---

## Output protocol

Templates produce strings. The orchestrator macro `generate_model` wraps each rendered string with delimiters and emits via `print()`:

```
<<<DBT_FORGE_FILE path="models/generated/foo.sql">>>
{{ config(materialized='view') }}

select
    *
from {{ source('raw', 'orders') }}
where status != 'cancelled'
<<<DBT_FORGE_END>>>
```

The CLI parses these blocks from dbt's stdout (regex match against `_BLOCK_RE` in `runner.py`) and writes the files. macros stay pure (no IO); the CLI does the bytes-on-disk work without any business logic of its own.

For `--dry-run` the open delimiter is `<<<DBT_FORGE_DRYRUN …>>>` instead, and the CLI prints rather than writes.
