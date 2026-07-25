"""
Mermaid renderers.

Output is a string containing a `graph LR` block, ready to paste in a Markdown
file (PRs, Notion, dbt docs) and have it rendered as an SVG.
"""

from __future__ import annotations

import re

from ..graph import GraphTraversal
from ..manifest import ManifestLoader, ManifestNode
from ..risk import NodeRisk, Risk

_INVALID_ID_CHARS = re.compile(r"[^A-Za-z0-9_]")


def _mermaid_id(unique_id: str) -> str:
    """Convert a unique_id into a Mermaid-safe node identifier.

    Mermaid IDs must match [A-Za-z][A-Za-z0-9_]*; we sanitize dots and dashes.
    """
    return _INVALID_ID_CHARS.sub("_", unique_id)


def _mermaid_shape(node: ManifestNode, label: str) -> str:
    """Pick a Mermaid shape based on resource type:
      - source:   cylinder    `id[("...")]`
      - exposure: hexagon-ish `id{{"..."}}`
      - default:  rectangle   `id["..."]`
    """
    if node.resource_type == "source":
        return f'{_mermaid_id(node.unique_id)}[("{label}")]'
    if node.resource_type == "exposure":
        return f'{_mermaid_id(node.unique_id)}{{{{"{label}"}}}}'
    return f'{_mermaid_id(node.unique_id)}["{label}"]'


# ---------------------------------------------------------------------------
# Lineage
# ---------------------------------------------------------------------------


def render_lineage_mermaid(
    *,
    root_node: ManifestNode,
    upstream: GraphTraversal | None,
    downstream: GraphTraversal | None,
    loader: ManifestLoader,
) -> str:
    lines: list[str] = ["graph LR"]
    declared: set[str] = set()
    edges: set[tuple[str, str]] = set()

    def declare(node: ManifestNode) -> None:
        if node.unique_id in declared:
            return
        declared.add(node.unique_id)
        lines.append("    " + _mermaid_shape(node, node.display_name))

    # Root declared with focus styling
    declare(root_node)

    for traversal in (upstream, downstream):
        if traversal is None:
            continue
        for uid in traversal.visited:
            node = loader.get(uid)
            if node is not None:
                declare(node)
        for parent, child in traversal.edges:
            edges.add((parent, child))

    lines.append("")
    for parent, child in sorted(edges):
        lines.append(f"    {_mermaid_id(parent)} --> {_mermaid_id(child)}")

    lines.append("")
    lines.append("    classDef focus fill:#fef3c7,stroke:#f59e0b,stroke-width:2px;")
    lines.append(f"    class {_mermaid_id(root_node.unique_id)} focus")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Impact
# ---------------------------------------------------------------------------


def render_impact_mermaid(*, root_node: ManifestNode, risks: list[NodeRisk]) -> str:
    """Mermaid graph of downstream nodes colored by risk level."""
    lines: list[str] = ["graph LR"]
    by_level: dict[Risk, list[str]] = {Risk.OK: [], Risk.WARNING: [], Risk.CRITICAL: []}

    lines.append("    " + _mermaid_shape(root_node, root_node.display_name))

    # Track parent-child edges as we go via depth ordering. We don't have the
    # full graph here, just the depth map, so we approximate by linking each
    # node back to the deepest ancestor present in our set. For a clean MVP,
    # render risks as independent nodes with their depth labeled.
    for r in risks:
        lines.append("    " + _mermaid_shape(r.node, f"{r.node.display_name}\\n[d{r.depth}]"))
        by_level[r.level].append(_mermaid_id(r.node.unique_id))

    # The root edges out to all depth-1 nodes
    root_mid = _mermaid_id(root_node.unique_id)
    for r in risks:
        if r.depth == 1:
            lines.append(f"    {root_mid} --> {_mermaid_id(r.node.unique_id)}")

    # Deeper edges: connect each depth-N node to the depth-(N-1) nodes it
    # actually depends on by looking up via the loader would be ideal, but
    # the renderer doesn't have the loader here. For v1 we draw a "skip" edge
    # from root for any node at depth >= 2 (clear at a glance even if not
    # structurally accurate). Future improvement: pass the loader/edges in.
    for r in risks:
        if r.depth >= 2:
            lines.append(f"    {root_mid} -.-> {_mermaid_id(r.node.unique_id)}")

    lines.append("")
    lines.append("    classDef ok fill:#d1fae5,stroke:#10b981;")
    lines.append("    classDef warn fill:#fef3c7,stroke:#f59e0b;")
    lines.append("    classDef crit fill:#fee2e2,stroke:#ef4444;")
    lines.append("    classDef focus fill:#dbeafe,stroke:#3b82f6,stroke-width:2px;")
    lines.append(f"    class {root_mid} focus")
    if by_level[Risk.OK]:
        lines.append(f"    class {','.join(by_level[Risk.OK])} ok")
    if by_level[Risk.WARNING]:
        lines.append(f"    class {','.join(by_level[Risk.WARNING])} warn")
    if by_level[Risk.CRITICAL]:
        lines.append(f"    class {','.join(by_level[Risk.CRITICAL])} crit")

    return "\n".join(lines) + "\n"
