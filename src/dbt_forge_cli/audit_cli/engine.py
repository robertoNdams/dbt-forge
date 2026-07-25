"""
Audit engine: runs the enabled rules against a manifest and aggregates findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..lineage_cli.manifest import ManifestLoader
from .rules import (
    DeadModels,
    InconsistentMaterialization,
    MissingColumnDescriptions,
    MissingModelDescription,
    MissingPrimaryKeyTest,
    ModelWithoutTests,
    OrphanSources,
    UndocumentedExposureDependencies,
)
from .rules.base import AuditRule, Finding, Severity


@dataclass
class AuditReport:
    """Aggregated result of running all enabled rules on a manifest."""

    findings: list[Finding] = field(default_factory=list)
    rules_run: list[str] = field(default_factory=list)
    total_models_scanned: int = 0

    @property
    def by_severity(self) -> dict[Severity, list[Finding]]:
        out: dict[Severity, list[Finding]] = {
            Severity.CRITICAL: [],
            Severity.WARNING: [],
            Severity.INFO: [],
        }
        for f in self.findings:
            out[f.severity].append(f)
        return out

    @property
    def max_severity(self) -> Severity | None:
        if not self.findings:
            return None
        worst = max(self.findings, key=lambda f: f.severity.severity)
        return worst.severity


class AuditEngine:
    """
    Runs a set of rules against a manifest.

    Usage:
        engine = AuditEngine()  # default rules
        report = engine.run(loader)
    """

    DEFAULT_RULES: list[type[AuditRule]] = [
        ModelWithoutTests,
        MissingPrimaryKeyTest,
        MissingModelDescription,
        MissingColumnDescriptions,
        OrphanSources,
        InconsistentMaterialization,
        DeadModels,
        UndocumentedExposureDependencies,
    ]

    def __init__(
        self,
        rules: list[type[AuditRule]] | None = None,
        *,
        select: set[str] | None = None,
        exclude: set[str] | None = None,
        severity_threshold: Severity = Severity.INFO,
    ) -> None:
        """
        rules: full rule classes to use (defaults to DEFAULT_RULES).
        select: only run rules whose code is in this set.
        exclude: drop rules whose code is in this set.
        severity_threshold: skip findings whose severity is below this level.
        """
        active = rules if rules is not None else list(self.DEFAULT_RULES)
        if select is not None:
            active = [r for r in active if r.code in select]
        if exclude is not None:
            active = [r for r in active if r.code not in exclude]
        self._rules: list[AuditRule] = [r() for r in active]
        self._threshold = severity_threshold

    def run(self, loader: ManifestLoader) -> AuditReport:
        report = AuditReport()
        report.rules_run = [r.code for r in self._rules]
        report.total_models_scanned = sum(
            1
            for n in loader.all_nodes().values()
            if n.resource_type == "model"
        )

        for rule in self._rules:
            for finding in rule.check(loader):
                if finding.severity.severity >= self._threshold.severity:
                    report.findings.append(finding)

        # Stable ordering: severity (worst first), then rule code, then node name
        report.findings.sort(
            key=lambda f: (-f.severity.severity, f.rule_code, f.node.name)
        )
        return report
