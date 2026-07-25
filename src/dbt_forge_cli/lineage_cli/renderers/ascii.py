"""
ASCII renderers for lineage and impact, using `rich` for tree drawing and
styling. These render to a console object passed in by the CLI — that way
tests can capture output via `Console(record=True)`.
"""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.tree import Tree

from ..graph import GraphTraversal
from ..manifest import ManifestLoader, ManifestNode
from ..risk import NodeRisk, Risk


# ---------------------------------------------------------------------------
# Lineage (`dbt-forge lineage`)
# ---------------------------------------------------------------------------


def render_lineage_ascii(
    console: Console,
    *,
    root_node: ManifestNode,
    upstream: GraphTraversal | None,
    downstream: GraphTraversal | None,
    loader: ManifestLoader,
    show_config: bool,
) -> None:
    """Print the lineage tree to `console`.

    Layout:
        <root>  [path]
        ├─ upstream
        │   └─ ...
        └─ downstream
            └─ ...

    Either tree can be None (when --no-upstream / --no-downstream is set).
    """
    root_label = _format_node(root_node, show_config=show_config, style="bold")
    tree = Tree(root_label)

    if upstream is not None:
        up_branch = tree.add("[dim]upstream[/dim]")
        _attach_traversal(
            up_branch,
            traversal=upstream,
            loader=loader,
            show_config=show_config,
            walk="parents",
        )
    if downstream is not None:
        down_branch = tree.add("[dim]downstream[/dim]")
        _attach_traversal(
            down_branch,
            traversal=downstream,
            loader=loader,
            show_config=show_config,
            walk="children",
        )

    console.print(tree)


def _attach_traversal(
    branch: Tree,
    *,
    traversal: GraphTraversal,
    loader: ManifestLoader,
    show_config: bool,
    walk: str,  # "parents" | "children"
) -> None:
    """Recursively attach the traversal tree to a rich.Tree node.

    The traversal stores depths; we rebuild the tree shape by walking from
    the root through neighbours, only recursing into nodes that the BFS
    visited (avoids cycles in case the DAG ever has them).
    """
    seen: set[str] = set()

    def recurse(parent_tree: Tree, current_uid: str) -> None:
        seen.add(current_uid)
        children_fn = loader.parents_of if walk == "parents" else loader.children_of
        for next_uid in children_fn(current_uid):
            if next_uid not in traversal.depths:
                continue
            if next_uid in seen:
                continue
            node = loader.get(next_uid)
            if node is None:
                continue
            child_tree = parent_tree.add(_format_node(node, show_config=show_config))
            recurse(child_tree, next_uid)

    recurse(branch, traversal.root)


def _format_node(node: ManifestNode, *, show_config: bool, style: str | None = None) -> str:
    r"""Format one node for ASCII display.

    Rich reads any ``[foo]`` sequence in the input as markup and swallows it.
    To display a literal opening bracket we escape it with a backslash — the
    raw f-string ``rf"\[foo]"`` produces the runtime string ``\[foo]``, which
    rich prints as ``[foo]``. The closing bracket does not need escaping.

    The path itself is run through ``rich.markup.escape()`` in case it ever
    contains characters that look like markup (rare, but the safety net is
    cheap).
    """
    label = node.display_name
    if style:
        label = f"[{style}]{label}[/{style}]"
    if show_config and node.file_path:
        label += rf"  [dim]\[{escape(node.file_path)}][/dim]"
    return label


# ---------------------------------------------------------------------------
# Impact (`dbt-forge impact`)
# ---------------------------------------------------------------------------


def render_impact_ascii(
    console: Console,
    *,
    root_node: ManifestNode,
    risks: list[NodeRisk],
    show_config: bool,
    show_tests: bool,
    show_exposures: bool,
) -> None:
    """Print the impact report.

    Format:
        Modifying <root> would affect N downstream nodes:

          IMMEDIATE (1 hop)
            <icon> <name>     [tests: N]  [exposures: M]  <reasons>
            ...

          DOWNSTREAM (2+ hops)
            ...

        Risk surface:
          ...
    """
    immediate = [r for r in risks if r.depth == 1]
    deeper = [r for r in risks if r.depth >= 2]

    total = len(risks)
    if total == 0:
        console.print(
            f"[bold]{root_node.display_name}[/bold] has no downstream models. "
            "Modifying it affects no other nodes."
        )
        return

    console.print(
        f"Modifying [bold]{root_node.display_name}[/bold] would affect "
        f"[bold]{total}[/bold] downstream node{'s' if total != 1 else ''}:\n"
    )

    if immediate:
        console.print("  [bold]IMMEDIATE[/bold] (1 hop)")
        for r in immediate:
            console.print("    " + _format_risk_line(r, show_config, show_tests, show_exposures))
        console.print()

    if deeper:
        console.print("  [bold]DOWNSTREAM[/bold] (2+ hops)")
        for r in deeper:
            console.print("    " + _format_risk_line(r, show_config, show_tests, show_exposures))
        console.print()

    _print_summary(console, risks)


def _format_risk_line(
    r: NodeRisk,
    show_config: bool,
    show_tests: bool,
    show_exposures: bool,
) -> str:
    r"""Format one line of the impact report.

    Same escape rule as _format_node: literal ``[`` is written as ``\[``
    using a raw f-string (``rf"\[...]"``).
    """
    color = {"ok": "green", "warning": "yellow", "critical": "red"}[r.level.value]
    parts = [f"[{color}]{r.level.icon}[/{color}] {r.node.display_name}"]

    if show_tests:
        marker = "" if r.tests_count else " [yellow]⚠[/yellow]"
        parts.append(rf"\[tests: {r.tests_count}{marker}]")
    if show_exposures:
        n = len(r.exposures)
        if n:
            names = ", ".join(e.name for e in r.exposures[:2])
            if n > 2:
                names += f", +{n - 2}"
            parts.append(rf"\[exposures: {n}: {escape(names)}]")
        else:
            parts.append(r"\[exposures: 0]")

    reasons = r.reasons
    if reasons:
        parts.append(f"[dim]({'; '.join(reasons)})[/dim]")

    line = "  ".join(parts)
    if show_config and r.node.file_path:
        line += rf"  [dim]\[{escape(r.node.file_path)}][/dim]"
    return line


def _print_summary(console: Console, risks: list[NodeRisk]) -> None:
    without_tests = sum(1 for r in risks if r.tests_count == 0)
    exposures_seen: set[str] = set()
    for r in risks:
        for e in r.exposures:
            exposures_seen.add(e.unique_id)
    critical = sum(1 for r in risks if r.level is Risk.CRITICAL)
    warning = sum(1 for r in risks if r.level is Risk.WARNING)

    by_type: dict[str, int] = {}
    for r in risks:
        by_type[r.node.resource_type] = by_type.get(r.node.resource_type, 0) + 1
    type_summary = ", ".join(f"{n} {t}{'s' if n != 1 else ''}" for t, n in sorted(by_type.items()))

    console.print("  [bold]Risk surface[/bold]")
    if without_tests:
        console.print(
            f"    [yellow]{without_tests}[/yellow] downstream node"
            f"{'s have' if without_tests != 1 else ' has'} no tests"
        )
    if exposures_seen:
        console.print(
            f"    [yellow]{len(exposures_seen)}[/yellow] exposure"
            f"{'s consume' if len(exposures_seen) != 1 else ' consumes'} this lineage"
        )
    if critical:
        console.print(f"    [red]{critical} critical[/red], [yellow]{warning} warning[/yellow]")
    elif warning:
        console.print(f"    [yellow]{warning} warning[/yellow]")
    console.print(f"    Total downstream: {type_summary}")
