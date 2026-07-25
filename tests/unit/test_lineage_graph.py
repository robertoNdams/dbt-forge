"""Tests for graph BFS traversal — upstream and downstream."""
from __future__ import annotations

from pathlib import Path

import pytest

from dbt_forge_cli.lineage_cli.graph import (
    traverse_downstream,
    traverse_upstream,
)
from dbt_forge_cli.lineage_cli.manifest import ManifestLoader

FIXTURE = Path(__file__).parent / "fixtures" / "manifest_sample.json"


@pytest.fixture(scope="module")
def loader() -> ManifestLoader:
    return ManifestLoader.from_path(FIXTURE)


def test_upstream_from_fct(loader):
    t = traverse_upstream(loader, "model.jaffle_shop.fct_revenue_per_customer")
    assert t.depths["model.jaffle_shop.fct_revenue_per_customer"] == 0
    assert t.depths["model.jaffle_shop.stg_orders"] == 1
    assert t.depths["source.jaffle_shop.raw.orders"] == 2
    # tests must NOT appear (default-excluded)
    assert not any(uid.startswith("test.") for uid in t.depths)


def test_downstream_from_stg_orders(loader):
    t = traverse_downstream(loader, "model.jaffle_shop.stg_orders")
    # Direct child
    assert t.depths["model.jaffle_shop.fct_revenue_per_customer"] == 1
    # 2-hop
    assert t.depths["model.jaffle_shop.rpt_top_customers"] == 2
    # Exposure beyond rpt_top_customers
    assert t.depths.get("exposure.jaffle_shop.executive_dashboard") == 3
    # No tests
    assert not any(uid.startswith("test.") for uid in t.depths)


def test_downstream_with_depth_limit(loader):
    t = traverse_downstream(
        loader, "model.jaffle_shop.stg_orders", max_depth=1
    )
    assert t.depths["model.jaffle_shop.fct_revenue_per_customer"] == 1
    # 2-hop must be missing
    assert "model.jaffle_shop.rpt_top_customers" not in t.depths


def test_upstream_at_leaf(loader):
    """Going upstream from a source: depth = 0 only."""
    t = traverse_upstream(loader, "source.jaffle_shop.raw.orders")
    assert t.depths == {"source.jaffle_shop.raw.orders": 0}


def test_downstream_at_terminal_model(loader):
    """Going downstream from a model with no children except exposure."""
    t = traverse_downstream(loader, "model.jaffle_shop.stg_customers")
    # Only itself, no children in the fixture
    assert list(t.depths.keys()) == ["model.jaffle_shop.stg_customers"]


def test_edges_are_recorded(loader):
    t = traverse_downstream(loader, "model.jaffle_shop.stg_orders")
    assert (
        "model.jaffle_shop.stg_orders",
        "model.jaffle_shop.fct_revenue_per_customer",
    ) in t.edges


def test_max_depth_property(loader):
    t = traverse_downstream(loader, "model.jaffle_shop.stg_orders")
    # stg_orders -> fct -> rpt -> exposure
    assert t.max_depth() == 3
