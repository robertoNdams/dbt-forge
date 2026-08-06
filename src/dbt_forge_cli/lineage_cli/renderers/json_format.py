"""
Machine-readable output for `dbt-forge impact`. This is the format that makes
the command usable in CI: pipe through `jq`, parse in a GitHub Action, etc.
"""

from __future__ import annotations

import json
from typing import Any

from ..manifest import ManifestNode
from ..risk import NodeRisk


def render_impact_json(
    *,
    root_node: ManifestNode,
    risks: list[NodeRisk],
) -> str:
    """Return a pretty-printed JSON string representing the impact report."""
    by_level: dict[str, int] = {"ok": 0, "warning": 0, "critical": 0}
    for r in risks:
        by_level[r.level.value] += 1

    exposures_seen: set[str] = set()
    for r in risks:
        for e in r.exposures:
            exposures_seen.add(e.unique_id)

    payload = {
        "target": {
            "name": root_node.name,
            "unique_id": root_node.unique_id,
            "file_path": root_node.file_path,
        },
        "downstream_count": len(risks),
        "nodes": [_node_payload(r) for r in risks],
        "summary": {
            "without_tests": sum(1 for r in risks if r.tests_count == 0),
            "exposures_affected": len(exposures_seen),
            "by_level": by_level,
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def _node_payload(r: NodeRisk) -> dict[str, Any]:
    return {
        "name": r.node.name,
        "unique_id": r.node.unique_id,
        "resource_type": r.node.resource_type,
        "file_path": r.node.file_path,
        "depth": r.depth,
        "tests_count": r.tests_count,
        "has_pk_test": r.has_pk_test,
        "exposures": [{"name": e.name, "unique_id": e.unique_id} for e in r.exposures],
        "level": r.level.value,
        "reasons": r.reasons,
    }
