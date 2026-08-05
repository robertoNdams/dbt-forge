"""Tests for ASCII, Mermaid, and JSON renderers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console

from dbt_forge_cli.lineage_cli.graph import (
    traverse_downstream,
    traverse_upstream,
)
from dbt_forge_cli.lineage_cli.manifest import ManifestLoader
from dbt_forge_cli.lineage_cli.renderers import (
    render_impact_ascii,
    render_impact_json,
    render_impact_mermaid,
    render_lineage_ascii,
    render_lineage_mermaid,
)
from dbt_forge_cli.lineage_cli.risk import classify_node

FIXTURE = Path(__file__).parent / "fixtures" / "manifest_sample.json"


@pytest.fixture(scope="module")
def loader() -> ManifestLoader:
    return ManifestLoader.from_path(FIXTURE)


@pytest.fixture
def console() -> Console:
    return Console(record=True, width=120, force_terminal=False, no_color=True)


# ---------------------------------------------------------------------------
# Lineage — ASCII
# ---------------------------------------------------------------------------


def test_lineage_ascii_basic(loader, console):
    root = loader.resolve("fct_revenue_per_customer")
    up = traverse_upstream(loader, root.unique_id)
    down = traverse_downstream(loader, root.unique_id)
    render_lineage_ascii(
        console,
        root_node=root,
        upstream=up,
        downstream=down,
        loader=loader,
        show_config=False,
    )
    output = console.export_text()
    assert "fct_revenue_per_customer" in output
    assert "stg_orders" in output
    assert "rpt_top_customers" in output
    assert "upstream" in output
    assert "downstream" in output


def test_lineage_ascii_with_config(loader, console):
    root = loader.resolve("fct_revenue_per_customer")
    up = traverse_upstream(loader, root.unique_id)
    render_lineage_ascii(
        console,
        root_node=root,
        upstream=up,
        downstream=None,
        loader=loader,
        show_config=True,
    )
    output = console.export_text()
    assert "models/generated/fct_revenue_per_customer.sql" in output
    assert "models/generated/stg_orders.sql" in output


def test_lineage_ascii_no_upstream(loader, console):
    root = loader.resolve("fct_revenue_per_customer")
    down = traverse_downstream(loader, root.unique_id)
    render_lineage_ascii(
        console,
        root_node=root,
        upstream=None,
        downstream=down,
        loader=loader,
        show_config=False,
    )
    output = console.export_text()
    assert "rpt_top_customers" in output
    # stg_orders is upstream and should not appear
    assert "stg_orders" not in output


# ---------------------------------------------------------------------------
# Lineage — Mermaid
# ---------------------------------------------------------------------------


def test_lineage_mermaid_basic(loader):
    root = loader.resolve("fct_revenue_per_customer")
    up = traverse_upstream(loader, root.unique_id)
    down = traverse_downstream(loader, root.unique_id)
    out = render_lineage_mermaid(root_node=root, upstream=up, downstream=down, loader=loader)
    assert out.startswith("graph LR\n")
    assert "fct_revenue_per_customer" in out
    assert "stg_orders" in out
    assert "-->" in out
    assert "classDef focus" in out


def test_lineage_mermaid_source_shape(loader):
    root = loader.resolve("stg_orders")
    up = traverse_upstream(loader, root.unique_id)
    out = render_lineage_mermaid(root_node=root, upstream=up, downstream=None, loader=loader)
    # source uses cylinder shape `[("...")]`
    assert '[("source: raw.orders")]' in out


# ---------------------------------------------------------------------------
# Impact — ASCII
# ---------------------------------------------------------------------------


def _build_risks(loader, root_uid: str):
    """Replicate the CLI command logic for tests."""
    downstream = traverse_downstream(loader, root_uid)
    risks = []
    for uid, hop in sorted(
        ((u, d) for u, d in downstream.depths.items() if u != root_uid),
        key=lambda x: (x[1], loader.get(x[0]).name if loader.get(x[0]) else ""),
    ):
        node = loader.get(uid)
        if node is None or node.resource_type == "exposure":
            continue
        risks.append(classify_node(loader, node, hop, exposures_for_root=[]))
    return risks


def test_impact_ascii_lists_downstream(loader, console):
    root = loader.resolve("stg_orders")
    risks = _build_risks(loader, root.unique_id)
    render_impact_ascii(
        console,
        root_node=root,
        risks=risks,
        show_config=False,
        show_tests=True,
        show_exposures=True,
    )
    out = console.export_text()
    assert "Modifying stg_orders" in out
    assert "fct_revenue_per_customer" in out
    assert "rpt_top_customers" in out
    assert "IMMEDIATE" in out
    assert "DOWNSTREAM" in out
    assert "tests:" in out
    assert "exposures:" in out


def test_impact_ascii_shows_critical_node(loader, console):
    """rpt_top_customers has no tests + downstream exposure -> critical."""
    root = loader.resolve("stg_orders")
    risks = _build_risks(loader, root.unique_id)
    render_impact_ascii(
        console,
        root_node=root,
        risks=risks,
        show_config=False,
        show_tests=True,
        show_exposures=True,
    )
    out = console.export_text()
    # Critical icon "✗" should appear next to rpt_top_customers
    # We can't easily test rich coloring in plain output, but the icon is text
    rpt_line = next(
        (line for line in out.splitlines() if "rpt_top_customers" in line),
        None,
    )
    assert rpt_line is not None
    assert "✗" in rpt_line


def test_impact_ascii_no_downstream(loader, console):
    """stg_customers has no children — print a friendly message."""
    root = loader.resolve("stg_customers")
    risks = _build_risks(loader, root.unique_id)
    render_impact_ascii(
        console,
        root_node=root,
        risks=risks,
        show_config=False,
        show_tests=True,
        show_exposures=True,
    )
    out = console.export_text()
    assert "no downstream models" in out


# ---------------------------------------------------------------------------
# Impact — JSON
# ---------------------------------------------------------------------------


def test_impact_json_well_formed(loader):
    root = loader.resolve("stg_orders")
    risks = _build_risks(loader, root.unique_id)
    out = render_impact_json(root_node=root, risks=risks)
    payload = json.loads(out)
    assert payload["target"]["name"] == "stg_orders"
    assert payload["downstream_count"] == len(risks)
    assert {"ok", "warning", "critical"} == set(payload["summary"]["by_level"].keys())
    rpt_entry = next(n for n in payload["nodes"] if n["name"] == "rpt_top_customers")
    assert rpt_entry["level"] == "critical"
    assert rpt_entry["depth"] == 2


# ---------------------------------------------------------------------------
# Impact — Mermaid
# ---------------------------------------------------------------------------


def test_impact_mermaid_includes_risk_classes(loader):
    root = loader.resolve("stg_orders")
    risks = _build_risks(loader, root.unique_id)
    out = render_impact_mermaid(root_node=root, risks=risks)
    assert "classDef crit" in out
    assert "classDef ok" in out
    assert "fct_revenue_per_customer" in out
