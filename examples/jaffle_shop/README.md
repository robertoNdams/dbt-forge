# Jaffle Shop — dbt-forge example

A complete, runnable example showing every dbt-forge feature against a tiny e-commerce dataset on **DuckDB**.

## What this demonstrates

| Model                          | Feature shown                                               |
| ------------------------------ | ----------------------------------------------------------- |
| `stg_customers`                | Plain staging from a raw source, column aliasing            |
| `stg_orders`                   | Filter (`WHERE status != 'cancelled'`)                      |
| `fct_revenue_per_customer`     | Aggregation (`SUM`, `COUNT`) + `GROUP BY` + `HAVING` + `ORDER BY` + materialized as `table` |
| `fct_high_value_revenue`       | CTE composition via `include_sources`, where the parent reads from the CTE |
| `schema.yml`                   | Generated tests (`not_null`, `unique`) and descriptions     |

The pre-generated output lives in `models/generated/` so you can inspect what dbt-forge produces without running anything.

## Run it

```bash
cd examples/jaffle_shop

# 1. Install dbt-duckdb (and dbt-forge if you haven't already)
uv pip install dbt-duckdb
uv pip install -e ../..    # install dbt-forge CLI from this repo

# 2. Pull the dbt_forge package locally
dbt deps --profiles-dir=.

# 3. Load seed data (creates `raw.customers` and `raw.orders` in DuckDB)
dbt seed --profiles-dir=.

# 4. (Re)generate models from the YAML config
dbt-forge generate \
  --config config/models.yml \
  --output-dir models/generated \
  --project-dir . \
  --profiles-dir=. \
  --overwrite

# 5. Build everything
dbt run --profiles-dir=.
dbt test --profiles-dir=.
```

You'll end up with a `jaffle_shop.duckdb` file in this directory containing all four generated models plus the seeds. Inspect it with:

```bash
duckdb jaffle_shop.duckdb -c "select * from main.fct_revenue_per_customer;"
```

## Re-generate after editing the config

Edit `config/models.yml` and re-run step 4. dbt-forge validates the config and lineage before invoking dbt; failures are reported with the exact YAML path that caused them.

To preview without writing files:

```bash
dbt-forge generate --config config/models.yml --output-dir models/generated --project-dir . --profiles-dir=. --dry-run
```
