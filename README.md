# dbt-forge

> **Config-driven dbt model generator** — composable, testable, dbt-native, future-proof.

[![CI](https://github.com/robertoNdams/dbt-forge/actions/workflows/ci.yml/badge.svg)](https://github.com/robertoNdams/dbt-forge/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![dbt 1.7+](https://img.shields.io/badge/dbt-1.7%2B-orange)](https://github.com/dbt-labs/dbt-core)

`dbt-forge` lets you describe dbt models as **intent** in YAML rather than writing SQL. A Python CLI validates your config and delegates to a dbt package made entirely of macros, which compose templates via `adapter.dispatch` to emit `.sql` files plus a matching `schema.yml`.

```text
config.yml  ──▶  CLI (Pydantic validation + lineage check)
                       │
                       ▼
              dbt run-operation generate_model
                       │
                       ▼
              dbt_forge macros (dispatch + compose)
                       │
                       ▼
              models/*.sql  +  models/schema.yml
```

---

## Why

Writing SQL by hand for hundreds of staging / mart models is repetitive. Existing dbt code-generators produce flat scaffolds; they don't compose. `dbt-forge` is built around three principles:

1. **Composition over templating** — every template is a macro that can call another macro. No `{% include %}`, no string concatenation in Python.
2. **dbt-native lineage** — the generator emits `ref()` and `source()` calls. Generated models participate fully in the dbt DAG.
3. **Override-friendly** — any project consuming `dbt_forge` can redefine `render_<template>` locally and it wins via `adapter.dispatch`.

---

## Repository layout

```
dbt-forge/
├── README.md
├── pyproject.toml                    # Python CLI package
├── src/dbt_forge_cli/                # Python: validation + orchestration only
│   ├── cli.py                        # `dbt-forge` entrypoint
│   ├── config.py                     # Pydantic schemas
│   ├── lineage.py                    # DAG validation (cycles, missing refs)
│   ├── runner.py                     # invokes `dbt run-operation`
│   └── validators/business_rules.py
├── dbt/dbt_forge/                    # dbt package — installable via packages.yml
│   ├── dbt_project.yml
│   └── macros/
│       ├── core/                     # generate_model, resolve_source, etc.
│       ├── templates/                # all 8 render_* templates
│       └── utils/                    # format_columns, format_filters, ...
├── examples/jaffle_shop/             # End-to-end working example (DuckDB)
├── tests/{unit,integration,fixtures}
└── docs/{DSL.md, TEMPLATES.md, EXTENDING.md}
```

---

## Installation

### 1. Install the CLI

```bash
uv pip install git+https://github.com/your-org/dbt-forge.git
# or, locally from the repo root:
uv pip install -e .
```

### 2. Add the dbt package to your project

`packages.yml`:

```yaml
packages:
  - git: https://github.com/your-org/dbt-forge.git
    subdirectory: dbt
```

```bash
dbt deps
```

---

## Quickstart

```yaml
# config/models.yml
models:
  - name: stg_orders
    description: "Cleaned orders staging."
    source: raw.orders
    template: full_select
    select_columns: ['*']
    filters:
      - column: status
        op: '!='
        value: 'cancelled'
    columns_meta:
      - name: order_id
        description: "Primary key."
        tests: [not_null, unique]

  - name: fct_revenue_per_customer
    description: "Total revenue per customer above threshold."
    source_model: stg_orders
    template: full_select
    select_columns: [customer_id]
    metrics:
      - name: total_revenue
        based_on: amount
        operation: sum
    breakdown_by: [customer_id]
    thresholds:
      - metric: total_revenue
        op: '>'
        value: 100
    sort_by:
      - metric: total_revenue
        order: desc
```

```bash
dbt-forge generate --config config/models.yml --output-dir models/generated
dbt run
```

The generator emits `models/generated/stg_orders.sql`, `models/generated/fct_revenue_per_customer.sql`, and a single `models/generated/schema.yml`.

---

## Running the example end-to-end

The repo ships a complete DuckDB example under [`examples/jaffle_shop/`](examples/jaffle_shop/) that exercises every feature of the DSL. The walk-through below shows the three phases in order — **validation**, **lineage**, **generation** — followed by the dbt build.

### Prerequisites

```bash
# From the repo root
uv pip install -e .            # installs the dbt-forge CLI
uv pip install dbt-duckdb      # adapter the example uses
cd examples/jaffle_shop
dbt deps --profiles-dir=.      # pulls in the dbt_forge package (local path)
dbt seed --profiles-dir=.      # loads customers.csv + orders.csv into raw.*
```

The example config is `config/models.yml` — four models covering staging, aggregation, HAVING/ORDER BY, and a CTE composition.

### Phase 1 — Validation only (no dbt invocation)

`dbt-forge validate` runs Pydantic schema checks plus business rules and exits without writing anything. Useful in CI on every PR.

```bash
dbt-forge validate --config config/models.yml
```

Expected output:

```
✓ 4 models valid · build order: stg_customers → stg_orders → fct_revenue_per_customer → fct_high_value_revenue
```

To see what failure looks like, edit `config/models.yml` and break something — say, change a threshold's `metric` to `ghost`:

```yaml
thresholds:
  - metric: ghost           # ← unknown metric
    op: '>'
    value: 100
```

Re-run the same command:

```
┃ Configuration errors                               ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ models.2                 │ Model 'fct_revenue_per_customer': threshold
│                          │ references unknown metric 'ghost'. Known
│                          │ metrics: ['n_orders', 'total_revenue'].
└──────────────────────────┴─────────────────────────┘
```

The CLI exits with code `1` and points to the YAML path. Revert the change to continue.

### Phase 2 — Lineage (DAG check)

Lineage validation runs as part of `validate`/`generate`, but you can see what it computed in the success line above (`build order: A → B → C → D`). To prove the cycle detector works, add a fake cycle to the config:

```yaml
- name: stg_customers
  source_model: fct_high_value_revenue   # introduce a cycle
  ...
```

```
╭─────────────────────────────────╮
│ Lineage validation failed       │
╰─────────────────────────────────╯
  • CYCLE: Cycle detected: stg_customers -> fct_high_value_revenue -> stg_orders -> stg_customers
```

External references (a `source_model` that isn't in the config) are **not** an error — they're delegated to dbt's own resolver and reported as informational:

```
External refs (delegated to dbt): some_external_model
✓ 4 models valid · build order: …
```

### Phase 3 — Generation (dry-run first, then write)

`--dry-run` prints the rendered SQL to stdout without touching the filesystem:

```bash
dbt-forge generate \
  --config config/models.yml \
  --output-dir models/generated \
  --project-dir . \
  --profiles-dir=. \
  --dry-run
```

Excerpt of what you'll see:

```sql
─── models/generated/fct_revenue_per_customer.sql ───
{{ config(materialized='table') }}

select
    customer_id,
    sum(amount) as total_revenue,
    count(order_id) as n_orders
from {{ ref('stg_orders') }}
group by customer_id
having total_revenue > 100
order by
    total_revenue desc

─── models/generated/fct_high_value_revenue.sql ───
{{ config(materialized='table') }}

with
paid_high_value as (
    select
        customer_id,
        amount
    from {{ ref('stg_orders') }}
    where amount >= 50
)

select
    customer_id,
    sum(amount) as hv_revenue
from paid_high_value
group by customer_id
order by
    hv_revenue desc
```

When the output looks right, drop `--dry-run` and add `--overwrite` to persist:

```bash
dbt-forge generate \
  --config config/models.yml \
  --output-dir models/generated \
  --project-dir . \
  --profiles-dir=. \
  --overwrite
```

```
✓ 4 models valid · build order: stg_customers → stg_orders → fct_revenue_per_customer → fct_high_value_revenue
  + examples/jaffle_shop/models/generated/stg_customers.sql
  + examples/jaffle_shop/models/generated/stg_orders.sql
  + examples/jaffle_shop/models/generated/fct_revenue_per_customer.sql
  + examples/jaffle_shop/models/generated/fct_high_value_revenue.sql
  + examples/jaffle_shop/models/generated/schema.yml
✓ Wrote 5 files to models/generated.
```

### Phase 4 — Build with dbt

The generated files are normal dbt models — `dbt run` and `dbt test` work without any further configuration:

```bash
dbt run --profiles-dir=.
dbt test --profiles-dir=.
```

```
Running with dbt=1.8.x
Found 4 models, 6 data tests, 2 sources, …

1 of 4 OK created sql view model main.stg_customers …………………… [OK in 0.07s]
2 of 4 OK created sql view model main.stg_orders ……………………… [OK in 0.06s]
3 of 4 OK created sql table model main.fct_revenue_per_customer  [OK in 0.09s]
4 of 4 OK created sql table model main.fct_high_value_revenue …  [OK in 0.08s]

Completed successfully
```

Inspect the warehouse:

```bash
duckdb jaffle_shop.duckdb -c "select * from main.fct_revenue_per_customer order by total_revenue desc;"
```

```
┌─────────────┬───────────────┬──────────┐
│ customer_id │ total_revenue │ n_orders │
├─────────────┼───────────────┼──────────┤
│      3      │     305.75    │     3    │
│      1      │     319.75    │     4    │
│      4      │     248.40    │     2    │
│      5      │     289.90    │     3    │
└─────────────┴───────────────┴──────────┘
```

### Iterating

Edit `config/models.yml`, re-run `dbt-forge generate --overwrite`, then `dbt run`. Validation + lineage are checked on every invocation, so a bad edit fails fast with a precise error rather than producing a broken `.sql`.

---

## DSL reference

| YAML key         | SQL equivalent      |
| ---------------- | ------------------- |
| `select_columns` | `SELECT`            |
| `filters`        | `WHERE`             |
| `metrics`        | aggregations        |
| `breakdown_by`   | `GROUP BY`          |
| `thresholds`     | `HAVING`            |
| `sort_by`        | `ORDER BY`          |

See [docs/DSL.md](docs/DSL.md) for the full spec.

---

## Templates & composition

Templates are pure macros named `render_<name>` in the `dbt_forge` namespace. They compose:

```
full_select
└── thresholds_select
    └── aggregation_select
        └── filtered_select
            └── distinct_select
                └── base_select
```

`render_ctes_select` wraps any of the above when `include_sources` is set.

To **override** a template, define a macro of the same name in your project — `adapter.dispatch` will pick it up automatically. See [docs/EXTENDING.md](docs/EXTENDING.md).

---

## CLI

```text
dbt-forge generate --config <path> --output-dir <dir> [options]

Options:
  --dry-run         Print rendered SQL without writing files
  --overwrite       Allow overwriting existing files
  --validate-only   Validate config + lineage and exit
  --project-dir     dbt project directory (default: .)
  --profiles-dir    dbt profiles directory
```

---

## Constraints (by design)

| ❌ Forbidden                              | ✅ Required                          |
| ----------------------------------------- | ------------------------------------ |
| `{% include %}`                           | macros only                          |
| File reads inside macros                  | `adapter.dispatch`                   |
| Business logic in Python (beyond config)  | `ref()` / `source()` for all sources |
| Hard-coded table names                    | clean CLI ⇄ dbt separation           |

---

## Development

### Setup

```bash
git clone https://github.com/robertoNdams/dbt-forge.git
cd dbt-forge
uv pip install -e ".[dev]"        # CLI + lint + test + integration extras
pre-commit install                # ruff format/lint + mypy + hygiene on every commit
```

### Running tests

| Command                                          | Scope                                       |
| ------------------------------------------------ | ------------------------------------------- |
| `pytest tests/unit`                              | Pydantic schema, lineage, render, parser    |
| `pytest tests/integration -m integration`        | Real dbt-duckdb run on the example project  |
| `pytest --cov=dbt_forge_cli`                     | All tests with coverage report              |
| `python tests/render_smoke.py`                   | Standalone macro smoke (no pytest needed)   |

The unit tests use a self-contained Jinja2 harness (`tests/jinja_harness.py`) that emulates dbt's `adapter.dispatch` — so no warehouse or dbt install is required. Integration tests are gated behind the `integration` marker and require `dbt-duckdb` (installed via the `[integration]` extra).

### Linting & type checking

```bash
ruff check src tests       # lint
ruff format src tests      # format (writes)
ruff format --check src tests  # format (CI mode, no writes)
mypy                       # configured to type-check src/dbt_forge_cli strictly
```

### CI/CD

Every push and PR to `main` or `dev` runs the full pipeline:

1. **Lint & type check** — ruff (lint + format) and mypy strict on the package
2. **Unit tests** — matrix across Python 3.10, 3.11, 3.12 with coverage uploaded as an artifact
3. **Integration** — installs `dbt-duckdb`, generates the example, runs `dbt run` + `dbt test`, asserts warehouse contents
4. **Build** — `python -m build` produces a wheel and sdist, both stored as artifacts

Workflows: [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

### Releases

Tag a commit with `vX.Y.Z` (matching `pyproject.toml`'s `project.version`) and push:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The [`release.yml`](.github/workflows/release.yml) workflow verifies the version match, builds the distributions, extracts the latest section from `CHANGELOG.md`, and creates a GitHub Release with the wheel and sdist attached.

### Dependency updates

Dependabot is configured in [`.github/dependabot.yml`](.github/dependabot.yml) with weekly grouped PRs for Python deps and GitHub Actions versions.

---

## License

MIT.
