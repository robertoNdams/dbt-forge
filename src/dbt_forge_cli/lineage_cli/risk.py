"""
Risk classification for `dbt-forge impact`.

A node's risk level is determined by a small set of heuristics. Default rules
(v1, in-code; configurable in a future version via .dbt-forge.yml):

  CRITICAL — the node is downstream of an exposure (something a human/system
             actually consumes) AND has no tests at all.
  WARNING  — the node has no tests, OR
             the node has tests but none on its primary key AND is downstream
             of an exposure.
  OK       — otherwise.

The "primary key" of a model is heuristic: we look for a `unique` or
`not_null` test on the first declared column. Imperfect but matches what most
projects do.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .manifest import ManifestLoader, ManifestNode


class Risk(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def icon(self) -> str:
        return {"ok": "✓", "warning": "⚠", "critical": "✗"}[self.value]

    @property
    def severity(self) -> int:
        """Numeric severity for --fail-on comparisons (higher = worse)."""
        return {"ok": 0, "warning": 1, "critical": 2}[self.value]


@dataclass(frozen=True)
class NodeRisk:
    node: ManifestNode
    depth: int
    tests_count: int
    has_pk_test: bool
    exposures: list[ManifestNode]
    level: Risk

    @property
    def reasons(self) -> list[str]:
        """Short human-readable explanations for the assigned level.

        Only emit the "exposures downstream" reason when the level is at
        least WARNING — for OK nodes, the exposure count is just context
        (already shown in the [exposures: N] column) and would be noise.
        """
        out: list[str] = []
        if self.tests_count == 0:
            out.append("no tests")
        elif not self.has_pk_test and self.level is not Risk.OK:
            out.append("no pk test")
        if self.exposures and self.level is not Risk.OK:
            out.append(f"{len(self.exposures)} exposure(s) downstream")
        return out


def classify_node(
    loader: ManifestLoader,
    node: ManifestNode,
    depth: int,
    *,
    exposures_for_root: list[ManifestNode],
) -> NodeRisk:
    """Build a NodeRisk for one node.

    `exposures_for_root` is the list of exposures reachable downstream from
    the impact root — passed in to avoid recomputing it per node. We refine
    it here by only counting exposures that *this specific node* would feed
    (i.e. exposures downstream of this node, not just of the root).
    """
    tests = loader.tests_attached_to(node.unique_id)
    has_pk_test = _has_pk_test(loader, node, tests)

    # Exposures downstream of THIS node specifically — refine the global set
    own_exposures = loader.exposures_downstream_of({node.unique_id})

    if tests == [] and own_exposures:
        level = Risk.CRITICAL
    elif tests == []:
        level = Risk.WARNING
    elif not has_pk_test and own_exposures:
        level = Risk.WARNING
    else:
        level = Risk.OK

    return NodeRisk(
        node=node,
        depth=depth,
        tests_count=len(tests),
        has_pk_test=has_pk_test,
        exposures=own_exposures,
        level=level,
    )


def _has_pk_test(
    loader: ManifestLoader,
    node: ManifestNode,
    tests: list[ManifestNode],
) -> bool:
    """Heuristic: does any attached test look like a uniqueness/not-null test
    on the model's primary key?

    We use the test's `name` field, which dbt encodes with a recognizable
    pattern such as `unique_<model>_<column>` or `not_null_<model>_<column>`.
    """
    pk_column = _guess_pk_column(loader, node)
    if pk_column is None:
        # No way to know the PK — fall back to "any unique test counts"
        return any(t.name.startswith(("unique_", "not_null_")) for t in tests)

    expected_uniq = f"unique_{node.name}_{pk_column}"
    expected_not_null = f"not_null_{node.name}_{pk_column}"
    return any(t.name in (expected_uniq, expected_not_null) for t in tests)


def _guess_pk_column(loader: ManifestLoader, node: ManifestNode) -> str | None:
    """Look up the node in the raw manifest and grab the first column declared
    in its `columns` mapping. Returns None if we can't find one.
    """
    raw = loader._raw.get("nodes", {}).get(node.unique_id)
    if not raw:
        return None
    columns = raw.get("columns")
    if not columns:
        return None
    # columns is an OrderedDict in manifest output, so the first key is the
    # first column declared in schema.yml. That's our PK heuristic.
    return next(iter(columns), None)
