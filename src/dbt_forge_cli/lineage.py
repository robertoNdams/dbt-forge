"""
Lineage validation: build the DAG implied by `source_model` references and
verify it is acyclic and fully resolvable.

A node is "external" when it is referenced via `source_model` but not defined
in the current config — this is allowed iff that name resolves to an existing
dbt model (we cannot check that from Python without invoking dbt; the CLI
defers that to dbt's own resolver and reports its error).
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import ForgeConfig, ModelConfig


@dataclass(frozen=True)
class LineageError:
    code: str  # "CYCLE" | "DUPLICATE" | "SELF_REFERENCE"
    message: str


@dataclass
class LineageReport:
    errors: list[LineageError]
    external_refs: set[str]  # source_model values not in config (delegated to dbt)
    topological_order: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _build_graph(cfg: ForgeConfig) -> tuple[dict[str, list[str]], set[str]]:
    """Return (adjacency, external_refs).

    Edge u -> v means "u depends on v" (v must be built first).
    """
    defined: set[str] = {m.name for m in cfg.models}
    adj: dict[str, list[str]] = {m.name: [] for m in cfg.models}
    external: set[str] = set()

    for m in cfg.models:
        deps = _collect_deps(m)
        for d in deps:
            if d in defined:
                adj[m.name].append(d)
            else:
                external.add(d)
    return adj, external


def _collect_deps(model: ModelConfig) -> list[str]:
    deps: list[str] = []
    if model.source_model:
        deps.append(model.source_model)
    for inc in model.include_sources:
        if inc.source_model:
            deps.append(inc.source_model)
    return deps


def validate_lineage(cfg: ForgeConfig) -> LineageReport:
    adj, external = _build_graph(cfg)
    errors: list[LineageError] = []

    # Self-references
    for node, deps in adj.items():
        if node in deps:
            errors.append(
                LineageError(
                    code="SELF_REFERENCE",
                    message=f"Model '{node}' references itself via source_model.",
                )
            )

    # Cycles via iterative DFS with WHITE/GRAY/BLACK coloring
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in adj}
    order: list[str] = []

    def visit(start: str) -> None:
        stack: list[tuple[str, int]] = [(start, 0)]
        path: list[str] = []
        while stack:
            node, idx = stack[-1]
            if idx == 0:
                if color[node] == GRAY:
                    cycle = [*path[path.index(node) :], node]
                    errors.append(
                        LineageError(
                            code="CYCLE",
                            message=(
                                "Cycle detected: " + " -> ".join(cycle)
                            ),
                        )
                    )
                    stack.pop()
                    continue
                if color[node] == BLACK:
                    stack.pop()
                    continue
                color[node] = GRAY
                path.append(node)
            neighbors = adj.get(node, [])
            if idx < len(neighbors):
                stack[-1] = (node, idx + 1)
                stack.append((neighbors[idx], 0))
            else:
                color[node] = BLACK
                if path and path[-1] == node:
                    path.pop()
                order.append(node)
                stack.pop()

    for n in list(adj.keys()):
        if color[n] == WHITE:
            visit(n)

    # If we found cycles the topo order is not meaningful
    topo = order if not any(e.code == "CYCLE" for e in errors) else []

    return LineageReport(errors=errors, external_refs=external, topological_order=topo)
