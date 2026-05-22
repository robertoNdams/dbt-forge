# Ruff lint fixes applied

All 20 violations from the CI run have been addressed in the source.

## Summary

| Rule    | Count | Files                                  | Fix                                                 |
| ------- | ----- | -------------------------------------- | --------------------------------------------------- |
| PTH201  | 1     | `src/dbt_forge_cli/cli.py`             | `Path(".")` → `Path()`                              |
| I001    | 1     | `src/dbt_forge_cli/config.py`          | resolved by removing `Union` (sort regression gone) |
| UP007   | 2     | `src/dbt_forge_cli/config.py`          | `Union[X, Y]` → `X \| Y`                            |
| UP037   | 8     | `src/dbt_forge_cli/config.py`          | strip quotes from forward refs (already have `from __future__ import annotations`) |
| RUF005  | 1     | `src/dbt_forge_cli/lineage.py`         | `a + [b]` → `[*a, b]`                               |
| RUF100  | 5     | `tests/`                               | remove unused `# noqa: E402` (ruff special-cases `pytest.importorskip` and `sys.path` mutations) |
| RUF043  | 2     | `tests/unit/test_config.py`            | regex `match="schema.table"` → `match=r"schema\.table"` |

Also pre-emptively cleaned `_metrics_require_breakdown` (was a no-op `pass` that would have tripped `PIE790`).

## Verification

```bash
ruff check src tests             # should now exit 0
ruff format --check src tests    # should now exit 0
mypy                              # should now exit 0
pytest tests/unit                 # all green
```
