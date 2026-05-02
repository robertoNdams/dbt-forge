"""
End-to-end integration test: validates that the dbt-forge CLI can
generate models from the example config, that dbt accepts the output,
and that the resulting warehouse contains the expected rows.

Skipped automatically when dbt-duckdb is not installed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("dbt.adapters.duckdb")  # actual import dbt-duckdb provides

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "examples" / "jaffle_shop"


pytestmark = pytest.mark.integration


@pytest.fixture
def example_dir(tmp_path: Path) -> Path:
    """Copy the example into a tmp dir so we don't pollute the repo."""
    target = tmp_path / "jaffle_shop"
    shutil.copytree(EXAMPLE, target)
    # Wipe any pre-existing generated artifacts so we test a real generation.
    gen = target / "models" / "generated"
    if gen.exists():
        shutil.rmtree(gen)
    return target


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        pytest.fail(
            f"Command failed: {' '.join(cmd)}\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )
    return proc


def test_full_pipeline(example_dir: Path) -> None:
    # 1. dbt deps — pulls in the local dbt_forge package
    _run(["dbt", "deps", "--profiles-dir=."], cwd=example_dir)

    # 2. dbt seed — load fixtures into raw.*
    _run(["dbt", "seed", "--profiles-dir=."], cwd=example_dir)

    # 3. dbt-forge generate — write the .sql + schema.yml files
    _run(
        [
            "dbt-forge", "generate",
            "--config", "config/models.yml",
            "--output-dir", "models/generated",
            "--project-dir", ".",
            "--profiles-dir=.",
            "--overwrite",
        ],
        cwd=example_dir,
    )

    # The four expected models + schema.yml exist
    gen = example_dir / "models" / "generated"
    assert (gen / "stg_customers.sql").exists()
    assert (gen / "stg_orders.sql").exists()
    assert (gen / "fct_revenue_per_customer.sql").exists()
    assert (gen / "fct_high_value_revenue.sql").exists()
    assert (gen / "schema.yml").exists()

    # Generated SQL contains the expected dbt references
    fct = (gen / "fct_revenue_per_customer.sql").read_text()
    assert "{{ ref('stg_orders') }}" in fct
    assert "having total_revenue > 100" in fct
    assert "order by" in fct

    # 4. dbt run — build the models
    _run(["dbt", "run", "--profiles-dir=."], cwd=example_dir)

    # 5. dbt test — run the generated tests (not_null, unique, etc.)
    _run(["dbt", "test", "--profiles-dir=."], cwd=example_dir)

    # 6. Sanity-check the warehouse: connect to DuckDB and assert the
    #    aggregation produced sensible numbers.
    import duckdb  # provided transitively by dbt-duckdb

    db = example_dir / "jaffle_shop.duckdb"
    assert db.exists()
    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = con.execute(
            "select count(*) from main.fct_revenue_per_customer"
        ).fetchone()
        assert rows is not None and rows[0] >= 1, "fct_revenue_per_customer is empty"

        # The HAVING clause should have filtered out customers with revenue <= 100
        min_rev = con.execute(
            "select min(total_revenue) from main.fct_revenue_per_customer"
        ).fetchone()
        assert min_rev is not None and min_rev[0] > 100
    finally:
        con.close()


def test_dry_run_does_not_write(example_dir: Path) -> None:
    """`--dry-run` should print SQL but not create files."""
    _run(["dbt", "deps", "--profiles-dir=."], cwd=example_dir)

    proc = _run(
        [
            "dbt-forge", "generate",
            "--config", "config/models.yml",
            "--output-dir", "models/generated",
            "--project-dir", ".",
            "--profiles-dir=.",
            "--dry-run",
        ],
        cwd=example_dir,
    )

    gen = example_dir / "models" / "generated"
    # No files should have been written
    sql_files = list(gen.glob("*.sql")) if gen.exists() else []
    assert sql_files == [], f"Dry-run wrote files: {sql_files}"

    # The rendered SQL should still appear somewhere in stdout
    assert "select" in proc.stdout.lower()


def test_validate_only_does_not_invoke_dbt(example_dir: Path) -> None:
    """`--validate-only` should never shell out to dbt."""
    proc = _run(
        [
            "dbt-forge", "generate",
            "--config", "config/models.yml",
            "--output-dir", "models/generated",
            "--project-dir", ".",
            "--validate-only",
        ],
        cwd=example_dir,
    )
    assert "models valid" in proc.stdout
    # Nothing should have been written either
    gen = example_dir / "models" / "generated"
    assert not (gen / "stg_orders.sql").exists()
