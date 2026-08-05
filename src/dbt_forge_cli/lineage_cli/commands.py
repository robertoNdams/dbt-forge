"""
Click command implementations for `dbt-forge lineage` and `dbt-forge impact`.

These are imported by `cli.py` and registered on the main `cli` group. We
keep them in their own module so `cli.py` stays focused on the existing
`generate` / `validate` commands and so the lineage code is fully isolated.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from .graph import traverse_downstream, traverse_upstream
from .manifest import (
    AmbiguousNodeError,
    ManifestError,
    ManifestLoader,
    ManifestNode,
    NodeNotFoundError,
)
from .renderers import (
    render_impact_ascii,
    render_impact_json,
    render_impact_mermaid,
    render_lineage_ascii,
    render_lineage_mermaid,
)
from .risk import classify_node

_console = Console()


def _load_manifest(
    project_dir: Path,
    target_dir: Path | None,
    profiles_dir: Path | None,
    no_parse: bool,
) -> ManifestLoader:
    try:
        return ManifestLoader.from_project(
            project_dir.resolve(),
            target_dir=target_dir,
            auto_parse=not no_parse,
            profiles_dir=profiles_dir.resolve() if profiles_dir else None,
        )
    except ManifestError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)


def _resolve(loader: ManifestLoader, name: str) -> ManifestNode:
    try:
        return loader.resolve(name)
    except NodeNotFoundError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except AmbiguousNodeError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# lineage
# ---------------------------------------------------------------------------


@click.command("lineage")
@click.argument("model_name")
@click.option(
    "--upstream/--no-upstream",
    default=True,
    show_default=True,
    help="Show ancestors.",
)
@click.option(
    "--downstream/--no-downstream",
    default=True,
    show_default=True,
    help="Show descendants.",
)
@click.option(
    "--depth",
    type=int,
    default=None,
    help="Limit traversal depth (unlimited by default).",
)
@click.option(
    "--show-config",
    is_flag=True,
    help="Show the file that defines each node.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["ascii", "mermaid"]),
    default="ascii",
    show_default=True,
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    default=Path(),
    show_default=True,
)
@click.option(
    "--target-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help="Directory containing manifest.json (defaults to <project-dir>/target).",
)
@click.option(
    "--profiles-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    default=None,
)
@click.option(
    "--no-parse",
    is_flag=True,
    help="Don't auto-run `dbt parse`. Fail if manifest.json is missing.",
)
def lineage(
    model_name: str,
    upstream: bool,
    downstream: bool,
    depth: int | None,
    show_config: bool,
    output_format: str,
    project_dir: Path,
    target_dir: Path | None,
    profiles_dir: Path | None,
    no_parse: bool,
) -> None:
    """Show upstream and downstream lineage for MODEL_NAME."""
    if not upstream and not downstream:
        _console.print(
            "[red]Both --no-upstream and --no-downstream are set — nothing to show.[/red]"
        )
        sys.exit(1)

    loader = _load_manifest(project_dir, target_dir, profiles_dir, no_parse)
    root = _resolve(loader, model_name)

    up = traverse_upstream(loader, root.unique_id, max_depth=depth) if upstream else None
    down = traverse_downstream(loader, root.unique_id, max_depth=depth) if downstream else None

    if output_format == "ascii":
        render_lineage_ascii(
            _console,
            root_node=root,
            upstream=up,
            downstream=down,
            loader=loader,
            show_config=show_config,
        )
    else:  # mermaid
        out = render_lineage_mermaid(
            root_node=root,
            upstream=up,
            downstream=down,
            loader=loader,
        )
        click.echo(out, nl=False)


# ---------------------------------------------------------------------------
# impact
# ---------------------------------------------------------------------------


@click.command("impact")
@click.argument("model_name")
@click.option(
    "--depth",
    type=int,
    default=None,
    help="Limit downstream depth (unlimited by default).",
)
@click.option(
    "--show-tests/--no-show-tests",
    default=True,
    show_default=True,
)
@click.option(
    "--show-exposures/--no-show-exposures",
    default=True,
    show_default=True,
)
@click.option(
    "--show-config",
    is_flag=True,
    help="Show the file that defines each node.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["ascii", "mermaid", "json"]),
    default="ascii",
    show_default=True,
)
@click.option(
    "--fail-on",
    type=click.Choice(["critical", "warning", "info"]),
    default=None,
    help="Exit non-zero if any downstream node has risk >= this level.",
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    default=Path(),
    show_default=True,
)
@click.option(
    "--target-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
)
@click.option(
    "--profiles-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    default=None,
)
@click.option(
    "--no-parse",
    is_flag=True,
)
def impact(
    model_name: str,
    depth: int | None,
    show_tests: bool,
    show_exposures: bool,
    show_config: bool,
    output_format: str,
    fail_on: str | None,
    project_dir: Path,
    target_dir: Path | None,
    profiles_dir: Path | None,
    no_parse: bool,
) -> None:
    """Show downstream impact and risk surface for MODEL_NAME."""
    loader = _load_manifest(project_dir, target_dir, profiles_dir, no_parse)
    root = _resolve(loader, model_name)

    # Downstream-only traversal — impact never goes upstream by definition.
    downstream = traverse_downstream(loader, root.unique_id, max_depth=depth)

    # Pre-compute exposures downstream of the root (for risk classification)
    all_exposures = loader.exposures_downstream_of({root.unique_id})

    # Build a risk record for every visited node except the root itself
    # Materialize (uid, depth, node) tuples first so the sort key doesn't have
    # to re-call loader.get() (and mypy can see the node is not None)
    resolved: list[tuple[str, int, ManifestNode]] = []
    for uid, d in downstream.depths.items():
        if uid == root.unique_id:
            continue
        node = loader.get(uid)
        if node is None:
            continue
        resolved.append((uid, d, node))
    resolved.sort(key=lambda t: (t[1], t[2].name))

    risks = []
    for _uid, hop, node in resolved:
        if node.resource_type == "exposure":
            # Don't classify exposure nodes themselves; they appear as
            # annotations on the upstream models they consume.
            continue
        risks.append(classify_node(loader, node, hop, exposures_for_root=all_exposures))

    if output_format == "ascii":
        render_impact_ascii(
            _console,
            root_node=root,
            risks=risks,
            show_config=show_config,
            show_tests=show_tests,
            show_exposures=show_exposures,
        )
    elif output_format == "mermaid":
        out = render_impact_mermaid(root_node=root, risks=risks)
        click.echo(out, nl=False)
    else:  # json
        out = render_impact_json(root_node=root, risks=risks)
        click.echo(out, nl=False)

    if fail_on is not None:
        threshold = {"info": 0, "warning": 1, "critical": 2}[fail_on]
        worst = max((r.level.severity for r in risks), default=0)
        if worst >= threshold:
            sys.exit(1)
