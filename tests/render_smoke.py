"""Drives the harness through every template layer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jinja_harness import build  # type: ignore[import-not-found]


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    h = build()

    # ------------------------------------------------------------------
    section("1. base_select on raw source")
    cfg = {
        "name": "stg_orders",
        "source": "raw.orders",
        "select_columns": ["order_id", "customer_id", "amount"],
        "filters": [],
        "metrics": [],
        "breakdown_by": [],
        "thresholds": [],
        "sort_by": [],
        "include_sources": [],
    }
    print(h.call("render_base_select", cfg))

    # ------------------------------------------------------------------
    section("2. distinct_select with select_columns")
    cfg2 = dict(cfg, select_columns=["customer_id", "country"], distinct=True)
    print(h.call("render_distinct_select", cfg2))

    # ------------------------------------------------------------------
    section("3. filtered_select with multiple filters")
    cfg3 = dict(
        cfg,
        filters=[
            {"column": "status", "op": "!=", "value": "cancelled"},
            {"column": "amount", "op": ">", "value": 0},
            {"column": "country", "op": "in", "value": ["FR", "DE", "ES"]},
            {"column": "deleted_at", "op": "is null", "value": None},
        ],
    )
    print(h.call("render_filtered_select", cfg3))

    # ------------------------------------------------------------------
    section("4. aggregation_select")
    cfg4 = {
        "name": "fct_revenue",
        "source_model": "stg_orders",
        "select_columns": ["customer_id"],
        "filters": [{"column": "status", "op": "=", "value": "paid"}],
        "metrics": [
            {"name": "total_revenue", "based_on": "amount", "operation": "sum"},
            {"name": "n_orders", "based_on": "order_id", "operation": "count"},
            {"name": "n_customers", "based_on": "customer_id", "operation": "count_distinct"},
        ],
        "breakdown_by": ["customer_id"],
        "thresholds": [],
        "sort_by": [],
        "include_sources": [],
    }
    print(h.call("render_aggregation_select", cfg4))

    # ------------------------------------------------------------------
    section("5. thresholds_select")
    cfg5 = dict(
        cfg4,
        thresholds=[{"metric": "total_revenue", "op": ">", "value": 100}],
    )
    print(h.call("render_thresholds_select", cfg5))

    # ------------------------------------------------------------------
    section("6. sorted_select on aggregated model")
    cfg6 = dict(
        cfg5,
        sort_by=[{"metric": "total_revenue", "order": "desc"}],
    )
    print(h.call("render_sorted_select", cfg6))

    # ------------------------------------------------------------------
    section("7. full_select on aggregated model (alias of sorted)")
    print(h.call("render_full_select", cfg6))

    # ------------------------------------------------------------------
    section("8. full_select on simple staging (no metrics)")
    cfg8 = {
        "name": "stg_clean_orders",
        "source": "raw.orders",
        "select_columns": ["order_id", "customer_id", "amount"],
        "filters": [{"column": "status", "op": "!=", "value": "cancelled"}],
        "metrics": [],
        "breakdown_by": [],
        "thresholds": [],
        "sort_by": [{"column": "order_id", "order": "asc"}],
        "include_sources": [],
    }
    print(h.call("render_full_select", cfg8))

    # ------------------------------------------------------------------
    section("9. ctes_select with include_sources")
    cfg9 = {
        "name": "fct_high_value_customers",
        "source_model": "paid_orders",  # references the CTE below
        "select_columns": ["customer_id"],
        "filters": [],
        "metrics": [{"name": "total", "based_on": "amount", "operation": "sum"}],
        "breakdown_by": ["customer_id"],
        "thresholds": [{"metric": "total", "op": ">", "value": 500}],
        "sort_by": [{"metric": "total", "order": "desc"}],
        "template": "full_select",
        "include_sources": [
            {
                "name": "paid_orders",
                "source_model": "stg_orders",
                "template": "filtered_select",
                "select_columns": ["customer_id", "amount"],
                "filters": [{"column": "status", "op": "=", "value": "paid"}],
            },
        ],
    }
    print(h.call("render_ctes_select", cfg9))

    # ------------------------------------------------------------------
    section("10. schema.yml builder")
    models = [
        {
            "name": "stg_orders",
            "description": "Cleaned orders.",
            "columns_meta": [
                {"name": "order_id", "description": "PK", "tests": ["not_null", "unique"]},
                {"name": "customer_id", "description": "FK to customers.", "tests": ["not_null"]},
                {"name": "amount", "tests": []},
            ],
        },
        {
            "name": "fct_revenue",
            "description": "Revenue per customer.",
            "columns_meta": [
                {"name": "customer_id", "tests": ["not_null", "unique"]},
                {"name": "total_revenue", "description": "Sum of paid amounts."},
            ],
        },
    ]
    print(h.call("build_schema_yml", models))


if __name__ == "__main__":
    main()
