# Changelog

## Unreleased

### Fixed
- `check_columns_meta_alignment` now correctly parses SQL aliases in `select_columns` (e.g. `id as customer_id`) when validating that every `columns_meta` entry exists in the produced output. Previously the validator treated the entire expression as the column name and reported false-positive `ORPHAN_COLUMN_META` errors.
- The validator now skips lenient-mode when at least one expression in `select_columns` is unparseable (e.g. a function call without an alias), instead of producing false positives.
- Integration test fixture rewrites `packages.yml` to an absolute path so `dbt deps` resolves the local `dbt_forge` package after the example is copied to a temp directory.

### Added
- `_produced_name` helper extracts the column an expression produces, supporting aliases (with optional double quotes), bare identifiers, and qualified names.
- `tests/unit/test_business_rules.py` covers the parser and the regression case from the failing CI run.

## 0.1.0 — Initial release

- CLI (`dbt-forge generate` / `dbt-forge validate`) with Pydantic config validation, lineage DAG check, and business rules.
- Eight composable templates: `base / distinct / filtered / aggregation / thresholds / sorted / full / ctes` `_select`.
- `adapter.dispatch`-based override surface for projects and warehouse adapters.
- Generated `schema.yml` with column-level descriptions and tests.
- Working DuckDB example (`examples/jaffle_shop`).
