# DSL Reference

The dbt-forge DSL is a YAML schema for describing dbt models as **intent**. The CLI validates it via Pydantic before any dbt invocation; this page documents every key, its type, and its semantics.

---

## Top-level

```yaml
version: 1
models:
  - <model>
  - <model>
```

| Key       | Type            | Required | Notes                                       |
| --------- | --------------- | -------- | ------------------------------------------- |
| `version` | `1`             | yes      | Schema version. Only `1` is currently valid. |
| `models`  | list of model   | yes      | Must be non-empty. Names must be unique.    |

---

## Model

```yaml
- name: stg_orders
  description: "Cleaned orders staging."
  source: raw.orders            # XOR with source_model
  source_model: stg_other       # XOR with source
  template: full_select         # default
  select_columns: ['*']
  distinct: false
  filters: []
  metrics: []
  breakdown_by: []
  thresholds: []
  sort_by: []
  include_sources: []
  output_type: view             # view | table | incremental
  columns_meta: []
```

### Identifiers

`name` must match `^[A-Za-z_][A-Za-z0-9_]*$`. Duplicates across the file are rejected.

### Source — exactly one of:

- **`source: <schema>.<table>`** → emits `{{ source('<schema>', '<table>') }}` in the generated SQL. The corresponding `source` must be declared in your dbt project's `sources.yml`.
- **`source_model: <name>`** → emits `{{ ref('<name>') }}`. Resolved through dbt's DAG; can be another generated model or a hand-written one.

If `source_model` matches a CTE name declared in `include_sources`, the generator emits a bare identifier (no `ref()`) — see the CTE section below.

### Template

`template` selects which `render_<name>` macro renders the model. Built-in values:

| Template               | Behavior                                        |
| ---------------------- | ----------------------------------------------- |
| `base_select`          | `select <cols> from <src>`                      |
| `distinct_select`      | adds `distinct`                                 |
| `filtered_select`      | adds `where`                                    |
| `aggregation_select`   | aggregates with `group by` (requires `metrics`) |
| `thresholds_select`    | aggregation + `having`                          |
| `sorted_select`        | wraps the right inner with `order by`           |
| `full_select` *(default)* | alias for `sorted_select`                    |
| `ctes_select`          | wraps any of the above with `with` + CTEs (auto-selected when `include_sources` is non-empty) |

You can register your own template — see [EXTENDING.md](EXTENDING.md).

### `select_columns`

List of column expressions. `'*'` is allowed and means "all columns from the source". Items are passed through verbatim, so `id as customer_id` and CASE expressions work.

### `distinct`

Boolean. When `true` the generator wraps the SELECT with `distinct`. Composed before `filters`.

### `filters` → `WHERE`

```yaml
filters:
  - column: status
    op: '!='
    value: 'cancelled'
  - column: amount
    op: '>'
    value: 0
  - column: country
    op: 'in'
    value: ['FR', 'DE', 'ES']
  - column: deleted_at
    op: 'is null'
```

Operators: `=`, `!=`, `>`, `>=`, `<`, `<=`, `like`, `in`, `not in`, `is null`, `is not null`.

Validation:
- `in` / `not in` require a list `value`.
- `is null` / `is not null` reject any `value`.
- Strings are quoted with `'…'` and embedded single-quotes are escaped to `''`. Numbers and bools are emitted literally.

### `metrics` → aggregations

```yaml
metrics:
  - name: total_revenue
    based_on: amount
    operation: sum
```

| Field       | Notes                                                        |
| ----------- | ------------------------------------------------------------ |
| `name`      | Column alias in the output. Must be unique within the model. |
| `based_on`  | Column the aggregation reads from.                            |
| `operation` | One of `count`, `count_distinct`, `sum`, `avg`, `min`, `max`. |

`count_distinct` renders as `count(distinct <col>)`.

### `breakdown_by` → `GROUP BY`

List of column names. Required (in practice) when `metrics` is non-empty — otherwise the aggregation collapses to a single row.

### `thresholds` → `HAVING`

```yaml
thresholds:
  - metric: total_revenue
    op: '>'
    value: 100
```

Same operator surface as `filters`, except `metric` references a name declared in `metrics`. The validator rejects references to unknown metrics.

### `sort_by` → `ORDER BY`

```yaml
sort_by:
  - metric: total_revenue
    order: desc
  - column: customer_id
    order: asc
```

Each item must specify exactly one of `metric` or `column`. References must resolve to a declared metric, a column in `select_columns`, or a column in `breakdown_by` (with `'*'` waiving the check).

### `include_sources` → CTEs

```yaml
include_sources:
  - name: paid_orders
    source_model: stg_orders
    template: filtered_select
    select_columns: [customer_id, amount]
    filters:
      - column: status
        op: '='
        value: 'paid'
```

Each item is itself a small model_cfg — it composes through the same templates. The generator emits each as a CTE in the order declared, then the parent model's main `SELECT` reads from one of them by setting `source_model: <cte_name>`.

When `include_sources` is non-empty, `ctes_select` is auto-selected regardless of the parent's `template`.

### `output_type` → materialization

`view` (default), `table`, `incremental`. Emitted as `{{ config(materialized='<value>') }}` at the top of the generated `.sql`.

### `columns_meta` → schema.yml

```yaml
columns_meta:
  - name: order_id
    description: "Primary key."
    tests: [not_null, unique]
```

Drives the generated `schema.yml`. Tests are passed through verbatim — anything dbt accepts (string shorthand for built-in tests, names of dbt-utils tests, etc.) works.

If `select_columns` is not `'*'`, the validator rejects `columns_meta` entries that aren't produced by the model.

---

## Validation pipeline

The CLI runs three layers, in order, and stops at the first failure:

1. **Pydantic schema** — types, enums, required fields, per-model XOR rules.
2. **Lineage** — DAG construction, cycle detection (DFS with WHITE/GRAY/BLACK coloring), topological order. References to undeclared models are treated as external (delegated to dbt's resolver).
3. **Business rules** — cross-model coherence (currently: orphan `columns_meta`).

Errors are formatted as a Rich table with the field path and message.
