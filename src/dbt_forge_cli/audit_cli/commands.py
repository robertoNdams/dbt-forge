"""
Click command for `dbt-forge audit`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from ..lineage_cli.manifest import ManifestError, ManifestLoader
from .engine import AuditEngine
from .renderers import render_audit_ascii, render_audit_json
from .rules.base import Severity

_console = Console()


def _parse_csv(value: str | None) -> set[str] | None:
    if value is None:
        return None
    return {part.strip() for part in value.split(",") if part.strip()}


@click.command("audit")
@click.option(
    "--select",
    "select_codes",
    type=str,
    default=None,
    help="Comma-separated list of rule codes to run (default: all).",
)
@click.option(
    "--exclude",
    "exclude_codes",
    type=str,
    default=None,
    help="Comma-separated list of rule codes to skip.",
)
@click.option(
    "--severity-threshold",
    type=click.Choice(["critical", "warning", "info"]),
    default="info",
    show_default=True,
    help="Hide findings below this severity level.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["ascii", "json"]),
    default="ascii",
    show_default=True,
)
@click.option(
    "--fail-on",
    type=click.Choice(["critical", "warning", "info"]),
    default=None,
    help="Exit non-zero if any finding's severity >= this level.",
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
    help="Don't auto-run `dbt parse`. Fail if manifest.json is missing.",
)
def audit(
    select_codes: str | None,
    exclude_codes: str | None,
    severity_threshold: str,
    output_format: str,
    fail_on: str | None,
    project_dir: Path,
    target_dir: Path | None,
    profiles_dir: Path | None,
    no_parse: bool,
) -> None:
    """Audit the dbt project for technical debt and missing coverage."""
    try:
        loader = ManifestLoader.from_project(
            project_dir.resolve(),
            target_dir=target_dir,
            auto_parse=not no_parse,
            profiles_dir=profiles_dir.resolve() if profiles_dir else None,
        )
    except ManifestError as e:
        _console.print(f"[red]{e}[/red]")
        sys.exit(2)

    engine = AuditEngine(
        select=_parse_csv(select_codes),
        exclude=_parse_csv(exclude_codes),
        severity_threshold=Severity(severity_threshold),
    )
    report = engine.run(loader)

    if output_format == "ascii":
        render_audit_ascii(_console, report)
    else:  # json
        out = render_audit_json(report)
        click.echo(out, nl=False)

    if fail_on is not None:
        threshold = Severity(fail_on).severity
        worst = report.max_severity.severity if report.max_severity else -1
        if worst >= threshold:
            sys.exit(1)
