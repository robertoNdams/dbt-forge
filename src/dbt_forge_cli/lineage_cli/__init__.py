"""
Lineage CLI sub-package.

Provides the implementation behind `dbt-forge lineage` and `dbt-forge impact`:
reads dbt's `manifest.json`, navigates the parent/child maps, and renders the
result as ASCII, Mermaid, or JSON.
"""

from .graph import GraphTraversal, traverse_downstream, traverse_upstream
from .manifest import (
    AmbiguousNodeError,
    ManifestError,
    ManifestLoader,
    ManifestNode,
    NodeNotFoundError,
)
from .risk import NodeRisk, Risk, classify_node

__all__ = [
    "AmbiguousNodeError",
    "GraphTraversal",
    "ManifestError",
    "ManifestLoader",
    "ManifestNode",
    "NodeNotFoundError",
    "NodeRisk",
    "Risk",
    "classify_node",
    "traverse_downstream",
    "traverse_upstream",
]
