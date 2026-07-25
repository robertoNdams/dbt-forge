"""Tests for the manifest loader: ingestion, name resolution, parent/child queries."""
from __future__ import annotations

from pathlib import Path

import pytest

from dbt_forge_cli.lineage_cli.manifest import (
    AmbiguousNodeError,
    ManifestError,
    ManifestLoader,
    NodeNotFoundError,
)

FIXTURE = Path(__file__).parent / "fixtures" / "manifest_sample.json"


@pytest.fixture(scope="module")
def loader() -> ManifestLoader:
    return ManifestLoader.from_path(FIXTURE)


def test_loads_all_node_types(loader):
    nodes = loader.all_nodes()
    by_type = {}
    for n in nodes.values():
        by_type.setdefault(n.resource_type, 0)
        by_type[n.resource_type] += 1
    assert by_type["model"] == 4
    assert by_type["source"] == 2
    assert by_type["test"] == 3
    assert by_type["exposure"] == 1


def test_resolve_short_name(loader):
    node = loader.resolve("stg_orders")
    assert node.unique_id == "model.jaffle_shop.stg_orders"
    assert node.name == "stg_orders"


def test_resolve_full_unique_id(loader):
    node = loader.resolve("model.jaffle_shop.stg_orders")
    assert node.name == "stg_orders"


def test_resolve_unknown_raises(loader):
    with pytest.raises(NodeNotFoundError, match="No node named 'ghost'"):
        loader.resolve("ghost")


def test_resolve_unknown_unique_id_raises(loader):
    with pytest.raises(NodeNotFoundError, match="model.foo.bar"):
        loader.resolve("model.foo.bar")


def test_parents_children(loader):
    parents = loader.parents_of("model.jaffle_shop.fct_revenue_per_customer")
    assert parents == ["model.jaffle_shop.stg_orders"]

    children = loader.children_of("model.jaffle_shop.stg_orders")
    # tests are included in child_map but graph traversal filters them out
    assert "model.jaffle_shop.fct_revenue_per_customer" in children


def test_tests_attached_to_model(loader):
    tests = loader.tests_attached_to("model.jaffle_shop.stg_orders")
    names = sorted(t.name for t in tests)
    assert names == [
        "not_null_stg_orders_order_id",
        "unique_stg_orders_order_id",
    ]


def test_exposures_downstream_of(loader):
    exposures = loader.exposures_downstream_of(
        {"model.jaffle_shop.stg_orders"}
    )
    names = [e.name for e in exposures]
    assert names == ["executive_dashboard"]


def test_exposures_downstream_terminal_leaf(loader):
    # stg_customers has no descendants — no exposures should be found
    exposures = loader.exposures_downstream_of(
        {"model.jaffle_shop.stg_customers"}
    )
    assert exposures == []


def test_display_name(loader):
    src = loader.resolve("orders", prefer_resource="source")
    assert "source: raw.orders" in src.display_name

    model = loader.resolve("stg_orders")
    assert model.display_name == "stg_orders"


def test_missing_manifest_raises():
    with pytest.raises(ManifestError, match="not found"):
        ManifestLoader.from_path(Path("/nonexistent/manifest.json"))
