"""Unit tests for lineage validation."""

from __future__ import annotations

import pytest

from dbt_forge_cli.config import ForgeConfig
from dbt_forge_cli.lineage import validate_lineage

pytest.importorskip("pydantic")


def _cfg(*models):
    return ForgeConfig.model_validate({"version": 1, "models": list(models)})


def test_simple_chain_topological():
    cfg = _cfg(
        {"name": "stg_orders", "source": "raw.orders", "select_columns": ["*"]},
        {"name": "fct_orders", "source_model": "stg_orders", "select_columns": ["*"]},
    )
    rep = validate_lineage(cfg)
    assert rep.ok
    assert rep.topological_order.index("stg_orders") < rep.topological_order.index("fct_orders")


def test_external_ref_does_not_error():
    cfg = _cfg(
        {"name": "fct_orders", "source_model": "external_thing", "select_columns": ["*"]},
    )
    rep = validate_lineage(cfg)
    assert rep.ok
    assert "external_thing" in rep.external_refs


def test_self_reference_detected():
    cfg = _cfg(
        {"name": "loop", "source_model": "loop", "select_columns": ["*"]},
    )
    rep = validate_lineage(cfg)
    assert not rep.ok
    assert any(e.code == "SELF_REFERENCE" for e in rep.errors)


def test_cycle_detected():
    cfg = _cfg(
        {"name": "a", "source_model": "b", "select_columns": ["*"]},
        {"name": "b", "source_model": "c", "select_columns": ["*"]},
        {"name": "c", "source_model": "a", "select_columns": ["*"]},
    )
    rep = validate_lineage(cfg)
    assert not rep.ok
    assert any(e.code == "CYCLE" for e in rep.errors)


def test_diamond_dag_is_acyclic():
    cfg = _cfg(
        {"name": "raw_layer", "source": "raw.t", "select_columns": ["*"]},
        {"name": "left", "source_model": "raw_layer", "select_columns": ["*"]},
        {"name": "right", "source_model": "raw_layer", "select_columns": ["*"]},
        {
            "name": "merged",
            "source_model": "left",
            "select_columns": ["*"],
            "include_sources": [
                {"name": "right_data", "source_model": "right", "select_columns": ["*"]}
            ],
        },
    )
    rep = validate_lineage(cfg)
    assert rep.ok, rep.errors
    order = rep.topological_order
    assert order.index("raw_layer") < order.index("left") < order.index("merged")
    assert order.index("right") < order.index("merged")
