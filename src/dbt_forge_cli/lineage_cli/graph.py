"""
Graph traversal over a ManifestLoader.

We build BFS walks from a root node, in either direction:
  - upstream:   follow parent_map (ancestors)
  - downstream: follow child_map (descendants)

The result is a `GraphTraversal` object holding:
  - the root unique_id
  - a depth map: unique_id -> hop count from the root (0 for the root itself)
  - an edges set: parent_uid -> child_uid pairs touched by the walk

Both `lineage` and `impact` consume this structure; the renderers do the rest.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .manifest import ManifestLoader

# Resource types we skip by default — they create visual noise without
# adding much value to a lineage view.
DEFAULT_EXCLUDED_TYPES: frozenset[str] = frozenset({"test", "analysis"})


@dataclass
class GraphTraversal:
    root: str
    direction: str  # "upstream" | "downstream" | "both"
    depths: dict[str, int] = field(default_factory=dict)
    edges: set[tuple[str, str]] = field(default_factory=set)

    @property
    def visited(self) -> set[str]:
        return set(self.depths.keys())

    def max_depth(self) -> int:
        return max(self.depths.values()) if self.depths else 0


def traverse_upstream(
    loader: ManifestLoader,
    root: str,
    *,
    max_depth: int | None = None,
    excluded_types: frozenset[str] = DEFAULT_EXCLUDED_TYPES,
) -> GraphTraversal:
    """BFS from `root` following parent_map. Edges are oriented parent → child."""
    return _bfs(
        loader=loader,
        root=root,
        neighbours=lambda uid: loader.parents_of(uid),
        edge_factory=lambda parent, child: (parent, child),  # parent is the neighbour
        max_depth=max_depth,
        excluded_types=excluded_types,
        direction="upstream",
    )


def traverse_downstream(
    loader: ManifestLoader,
    root: str,
    *,
    max_depth: int | None = None,
    excluded_types: frozenset[str] = DEFAULT_EXCLUDED_TYPES,
) -> GraphTraversal:
    """BFS from `root` following child_map. Edges are oriented parent → child."""
    return _bfs(
        loader=loader,
        root=root,
        neighbours=lambda uid: loader.children_of(uid),
        edge_factory=lambda current, child: (current, child),
        max_depth=max_depth,
        excluded_types=excluded_types,
        direction="downstream",
    )


def _bfs(
    *,
    loader: ManifestLoader,
    root: str,
    neighbours: Callable[[str], Iterable[str]],
    edge_factory: Callable[[str, str], tuple[str, str]],
    max_depth: int | None,
    excluded_types: frozenset[str],
    direction: str,
) -> GraphTraversal:
    traversal = GraphTraversal(root=root, direction=direction)
    traversal.depths[root] = 0

    queue: deque[str] = deque([root])
    while queue:
        current = queue.popleft()
        current_depth = traversal.depths[current]
        if max_depth is not None and current_depth >= max_depth:
            continue
        for neigh in neighbours(current):
            neigh_node = loader.get(neigh)
            if neigh_node is None:
                continue
            if neigh_node.resource_type in excluded_types:
                continue
            traversal.edges.add(edge_factory(current, neigh))
            if neigh not in traversal.depths:
                traversal.depths[neigh] = current_depth + 1
                queue.append(neigh)
    return traversal
