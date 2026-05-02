# Changelog

## 0.1.0 — Initial release

- CLI (`dbt-forge generate` / `dbt-forge validate`) with Pydantic config validation, lineage DAG check, and business rules.
- Eight composable templates: `base / distinct / filtered / aggregation / thresholds / sorted / full / ctes` `_select`.
- `adapter.dispatch`-based override surface for projects and warehouse adapters.
- Generated `schema.yml` with column-level descriptions and tests.
- Working DuckDB example (`examples/jaffle_shop`).
