"""
`dbt-forge` CLI.

Subcommands:
  generate   — validate config + lineage, then dispatch to dbt run-operation.
  validate   — validate config + lineage only (alias for `generate --validate-only`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import ForgeConfig
from .lineage import validate_lineage
from .runner import (
    DbtNotFoundError,
    DbtRunError,
    FileExistsConflict,
    RunnerOptions,
    invoke_generate_model,
)
from .validators import run_all as run_business_rules

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        console.print(f"[red]Config file not found:[/red] {path}")
        sys.exit(2)
    with path.open() as fh:
        try:
            return yaml.safe_load(fh) or {}
        except yaml.YAMLError as e:
            console.print(f"[red]YAML parse error in {path}:[/red] {e}")
            sys.exit(2)


def _print_validation_error(e: ValidationError) -> None:
    table = Table(title="Configuration errors", show_lines=True)
    table.add_column("Location", style="cyan", no_wrap=True)
    table.add_column("Message", style="white")
    for err in e.errors():
        loc = ".".join(str(p) for p in err["loc"])
        table.add_row(loc or "(root)", err["msg"])
    console.print(table)


def _validate(cfg_path: Path) -> ForgeConfig:
    raw = _load_yaml(cfg_path)
    try:
        cfg = ForgeConfig.model_validate(raw)
    except ValidationError as e:
        _print_validation_error(e)
        sys.exit(1)

    lineage = validate_lineage(cfg)
    if not lineage.ok:
        console.print(Panel.fit("[red]Lineage validation failed[/red]"))
        for lin_err in lineage.errors:
            console.print(f"  • [yellow]{lin_err.code}[/yellow]: {lin_err.message}")
        sys.exit(1)

    rule_errors = run_business_rules(cfg)
    if rule_errors:
        console.print(Panel.fit("[red]Business-rule validation failed[/red]"))
        for rule_err in rule_errors:
            console.print(
                f"  • [magenta]{rule_err.model}[/magenta] [yellow]{rule_err.code}[/yellow]: {rule_err.message}"
            )
        sys.exit(1)

    if lineage.external_refs:
        console.print(
            f"[dim]External refs (delegated to dbt):[/dim] "
            f"{', '.join(sorted(lineage.external_refs))}"
        )
    console.print(
        f"[green]✓[/green] {len(cfg.models)} models valid · "
        f"build order: {' → '.join(lineage.topological_order)}"
    )
    return cfg


# ---------------------------------------------------------------------------
# Click commands
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(package_name="dbt-forge")
def cli() -> None:
    """Config-driven dbt model generator."""


@cli.command()
@click.option("--config", "config_path", type=click.Path(path_type=Path), required=True)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    required=True,
    help=(
        "Directory under your dbt project where .sql + schema.yml will be written. "
        "Relative to --project-dir."
    ),
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    default=Path(),
    show_default=True,
)
@click.option(
    "--profiles-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    default=None,
)
@click.option("--dry-run", is_flag=True, help="Render to stdout instead of writing files.")
@click.option("--overwrite", is_flag=True, help="Overwrite existing files.")
@click.option(
    "--validate-only",
    is_flag=True,
    help="Validate config + lineage without invoking dbt.",
)
def generate(
    config_path: Path,
    output_dir: Path,
    project_dir: Path,
    profiles_dir: Path | None,
    dry_run: bool,
    overwrite: bool,
    validate_only: bool,
) -> None:
    """Generate dbt models from a YAML config."""
    cfg = _validate(config_path)
    if validate_only:
        return

    opts = RunnerOptions(
        project_dir=project_dir.resolve(),
        profiles_dir=profiles_dir.resolve() if profiles_dir else None,
        output_dir=output_dir,
        overwrite=overwrite,
        dry_run=dry_run,
    )

    try:
        result = invoke_generate_model(cfg, opts)
    except DbtNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(127)
    except FileExistsConflict as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except DbtRunError as e:
        console.print(f"[red]dbt failed (exit {e.returncode}):[/red]\n{e.stderr or e.stdout}")
        sys.exit(e.returncode or 1)

    if dry_run:
        for emitted in result.dry_run_files:
            console.rule(f"[cyan]{emitted.path}[/cyan]")
            console.print(emitted.body)
        console.print(
            f"[green]✓[/green] Dry-run complete · {len(result.dry_run_files)} files would be written."
        )
        return

    for p in result.written:
        console.print(f"  [green]+[/green] {p}")
    for p in result.skipped:
        console.print(f"  [yellow]·[/yellow] {p} (exists, skipped)")
    console.print(
        f"[green]✓[/green] Wrote {len(result.written)} files to [cyan]{output_dir}[/cyan]."
    )


@cli.command()
@click.option("--config", "config_path", type=click.Path(path_type=Path), required=True)
def validate(config_path: Path) -> None:
    """Validate config + lineage without invoking dbt."""
    _validate(config_path)


def main() -> None:  # entrypoint for pyproject.toml [project.scripts]
    cli()


if __name__ == "__main__":
    main()
