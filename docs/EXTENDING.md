# Extending dbt-forge

Two scenarios:

1. **Add a new template** — a new render strategy that users opt into via `template: <name>`.
2. **Override an existing template** — change how an existing template renders for your project (or for one warehouse).

---

## 1. Add a new template

Drop a macro into your dbt project's `macros/` folder:

```jinja
{# macros/render_pivot_select.sql #}
{% macro render_pivot_select(model_cfg) %}
    {{- adapter.dispatch('default__render_pivot_select', 'dbt_forge')(model_cfg) -}}
{% endmacro %}

{% macro default__render_pivot_select(model_cfg) %}
    {%- set src = dbt_forge.resolve_source(model_cfg) -%}
    {%- set pivot_col = model_cfg.pivot_on -%}
    {%- set pivot_values = model_cfg.pivot_values -%}

select
    {{ model_cfg.row_key }},
    {%- for v in pivot_values %}
    sum(case when {{ pivot_col }} = '{{ v }}' then amount else 0 end) as amt_{{ v }}{{ "," if not loop.last }}
    {%- endfor %}
from {{ src }}
group by {{ model_cfg.row_key }}
{% endmacro %}
```

The macro **must** live in the `dbt_forge` dispatch namespace path, which means it must be in *your* project's macros (or in a package whose `dispatch` is configured to dbt_forge — see the `dispatch` config below).

Use it from YAML:

```yaml
- name: revenue_by_country
  source_model: stg_orders
  template: pivot_select
  pivot_on: country
  pivot_values: [FR, DE, ES]
  row_key: customer_id
```

dbt-forge's Pydantic schema does not know about your custom fields. Two options:

- **Permissive mode**: keep them at the model level — Pydantic's `extra="forbid"` will reject them. To allow them you can vendor a fork of `config.py` with `extra="allow"`, or stick the custom fields under a single namespace (e.g. `extra: { pivot_on: country, ... }`) and reference `model_cfg.extra.pivot_on` from the macro.
- **Strict mode**: add the new fields to `config.py` and rebuild the CLI. Recommended for production deployments.

---

## 2. Override an existing template

Define a macro of the same name in your project. Dispatch picks it up automatically because dbt searches the **calling project** before the package:

```jinja
{# macros/render_filtered_select.sql — in YOUR project, not in dbt_forge #}
{% macro render_filtered_select(model_cfg) %}
    {%- set inner = dbt_forge.render_base_select(model_cfg) -%}
    {%- set filters = model_cfg.get('filters', []) -%}
    {%- if filters | length == 0 -%}
        {{- inner -}}
    {%- else -%}
{{ inner }}
where 1=1   -- our team standard: keep WHERE as a multi-line conjunction
  {%- for f in filters %}
  and {{ dbt_forge.forge_format_one_filter(f) }}
  {%- endfor %}
    {%- endif -%}
{% endmacro %}
```

Now every model in your project that uses `template: full_select` (which composes `filtered_select`) gets your override.

---

## 3. Adapter-specific implementations

If you need different SQL on Snowflake vs BigQuery, define `<adapter>__<name>` variants:

```jinja
{% macro snowflake__render_aggregation_select(model_cfg) %}
    -- Snowflake-specific: use APPROX_COUNT_DISTINCT for count_distinct
    ...
{% endmacro %}

{% macro bigquery__render_aggregation_select(model_cfg) %}
    ...
{% endmacro %}
```

`adapter.dispatch` resolves in order: `<active_adapter>__<name>` → `default__<name>`. Place these alongside the package or in your project — both are searched.

---

## 4. The `dispatch` config (advanced)

If you ship a separate dbt package (say `acme_dbt_extensions`) and want **its** macros to be discovered as overrides for `dbt_forge`'s renderers, add to the consuming project's `dbt_project.yml`:

```yaml
dispatch:
  - macro_namespace: dbt_forge
    search_order: ['acme_dbt_extensions', 'my_project', 'dbt_forge']
```

dbt will look up `render_<name>` in that order before falling back to the bundled `default__` implementation.

---

## 5. Adding new business-rule validators

Cross-model validators live in `src/dbt_forge_cli/validators/business_rules.py`. Add a function that takes a `ForgeConfig` and returns a list of `BusinessRuleError`, then register it in `run_all`:

```python
def check_no_self_join(cfg: ForgeConfig) -> list[BusinessRuleError]:
    errors: list[BusinessRuleError] = []
    for m in cfg.models:
        for inc in m.include_sources:
            if inc.source_model == m.name:
                errors.append(BusinessRuleError(
                    model=m.name,
                    code="SELF_JOIN",
                    message=f"include_source '{inc.name}' references the parent model.",
                ))
    return errors


def run_all(cfg):
    return [
        *check_columns_meta_alignment(cfg),
        *check_no_self_join(cfg),
    ]
```

Re-install the CLI (`uv pip install -e .`) and your new check runs on every `dbt-forge generate`.

---

## 6. Testing your extensions

Reuse the Jinja smoke harness in `tests/jinja_harness.py` — it loads every `.sql` file under `dbt/dbt_forge/macros/`. Symlink your project's macro folder into that tree (or extend the `_collect_macros` walk) and you can write Python-level assertions against the rendered SQL without spinning up dbt or a warehouse.
