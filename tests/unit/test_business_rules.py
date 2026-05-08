"""Tests for the SELECT-list alias parser used by columns_meta validation."""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from dbt_forge_cli.config import ForgeConfig
from dbt_forge_cli.validators.business_rules import (
    _exposed_columns,
    _produced_name,
    check_columns_meta_alignment,
)


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("id", "id"),
        ("customer_id", "customer_id"),
        ("id as customer_id", "customer_id"),
        ("id AS customer_id", "customer_id"),
        ("id  As  customer_id", "customer_id"),
        ("user_id as customer_id", "customer_id"),
        ("schema.t.col", "col"),
        ("trim(email) as email", "email"),
        ('id as "customer_id"', "customer_id"),
        ("trim(email)", None),
        ("substring(x, 1, 5)", None),
        ("*", None),
        ("", None),
    ],
)
def test_produced_name(expr: str, expected: str | None) -> None:
    assert _produced_name(expr) == expected


def test_exposed_columns_with_only_aliases() -> None:
    exposed, has_unknown = _exposed_columns(
        ["id as customer_id", "first_name", "last_name", "email"]
    )
    assert exposed == {"customer_id", "first_name", "last_name", "email"}
    assert has_unknown is False


def test_exposed_columns_marks_unknown_when_unparseable() -> None:
    exposed, has_unknown = _exposed_columns(["id", "trim(email)", "amount"])
    assert exposed == {"id", "amount"}
    assert has_unknown is True


def test_columns_meta_passes_with_aliased_select() -> None:
    """The bug from CI: 'id as customer_id' should expose 'customer_id'."""
    cfg = ForgeConfig.model_validate(
        {
            "version": 1,
            "models": [
                {
                    "name": "stg_customers",
                    "source": "raw.customers",
                    "select_columns": [
                        "id as customer_id",
                        "first_name",
                        "last_name",
                        "email",
                    ],
                    "columns_meta": [
                        {"name": "customer_id", "tests": ["not_null", "unique"]},
                        {"name": "email", "tests": ["not_null"]},
                    ],
                }
            ],
        }
    )
    errors = check_columns_meta_alignment(cfg)
    assert errors == []


def test_columns_meta_still_catches_real_orphans() -> None:
    cfg = ForgeConfig.model_validate(
        {
            "version": 1,
            "models": [
                {
                    "name": "stg_orders",
                    "source": "raw.orders",
                    "select_columns": ["id as order_id", "amount"],
                    "columns_meta": [
                        {"name": "ghost", "tests": ["not_null"]},
                    ],
                }
            ],
        }
    )
    errors = check_columns_meta_alignment(cfg)
    assert len(errors) == 1
    assert errors[0].code == "ORPHAN_COLUMN_META"
    assert "ghost" in errors[0].message


def test_columns_meta_lenient_on_unparseable_expressions() -> None:
    """If we can't statically parse one expr, don't flag any meta as orphan."""
    cfg = ForgeConfig.model_validate(
        {
            "version": 1,
            "models": [
                {
                    "name": "stg_x",
                    "source": "raw.x",
                    "select_columns": ["id", "trim(email)"],  # 2nd expr is opaque
                    "columns_meta": [
                        {"name": "id"},
                        {"name": "email"},  # would be 'orphan' under strict parsing
                    ],
                }
            ],
        }
    )
    errors = check_columns_meta_alignment(cfg)
    assert errors == []
