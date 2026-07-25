"""
ASCII renderer for the audit report — grouped by severity, with suggestions.
"""

from __future__ import annotations

from rich.console import Console

from ..engine import AuditReport
from ..rules.base import Finding, Severity


def render_audit_ascii(console: Console, report: AuditReport) -> None:
    """Print the audit report to `console`.

    Format:
        Scanning N models, ... rules: AUDIT001, AUDIT002, ...

        CRITICAL  (3)
          AUDIT002  Model 'X' has tests but no PK test
                    → Add a unique/not_null on 'foo' in models/schema.yml

        WARNING   (5)
          ...

        INFO      (12)
          ...

        Summary: 20 findings across 14 models.
    """
    rules_str = ", ".join(report.rules_run) if report.rules_run else "(none)"
    console.print(
        f"Scanned [bold]{report.total_models_scanned}[/bold] model"
        f"{'s' if report.total_models_scanned != 1 else ''}, "
        f"ran {len(report.rules_run)} rule"
        f"{'s' if len(report.rules_run) != 1 else ''}: [dim]{rules_str}[/dim]\n"
    )

    if not report.findings:
        console.print("[green]✓ No issues found.[/green]")
        return

    grouped = report.by_severity
    for severity in (Severity.CRITICAL, Severity.WARNING, Severity.INFO):
        items = grouped[severity]
        if not items:
            continue
        color = {"info": "cyan", "warning": "yellow", "critical": "red"}[severity.value]
        console.print(
            f"[bold {color}]{severity.value.upper():<9}[/bold {color}] "
            f"([{color}]{len(items)}[/{color}])"
        )
        for f in items:
            _render_finding(console, f, color)
        console.print()

    _print_summary(console, report)


def _render_finding(console: Console, f: Finding, color: str) -> None:
    """One finding block: code, message, optional suggestion."""
    console.print(f"  [{color}]{f.rule_code}[/{color}]  {f.message}")
    if f.suggestion:
        console.print(f"           [dim]→ {f.suggestion}[/dim]")


def _print_summary(console: Console, report: AuditReport) -> None:
    by_sev = report.by_severity
    affected_models = len({f.node.unique_id for f in report.findings})

    parts = []
    if by_sev[Severity.CRITICAL]:
        parts.append(f"[red]{len(by_sev[Severity.CRITICAL])} critical[/red]")
    if by_sev[Severity.WARNING]:
        parts.append(f"[yellow]{len(by_sev[Severity.WARNING])} warning[/yellow]")
    if by_sev[Severity.INFO]:
        parts.append(f"[cyan]{len(by_sev[Severity.INFO])} info[/cyan]")
    severity_summary = ", ".join(parts)

    console.print(
        f"[bold]Summary[/bold]: {len(report.findings)} finding"
        f"{'s' if len(report.findings) != 1 else ''} "
        f"across {affected_models} node"
        f"{'s' if affected_models != 1 else ''} "
        f"({severity_summary})"
    )
