"""
Abstract base for audit rules.

Contract: every rule has a unique code (AUDITxxx), a fixed severity, a human
description, and a check() method that scans a ManifestLoader and yields
Finding objects.

Severity is part of the rule definition rather than per-finding because we
want predictable behavior in CI (`--fail-on warning` always means the same
thing across rules, regardless of which model triggered it).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from ...lineage_cli.manifest import ManifestLoader, ManifestNode


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def icon(self) -> str:
        return {"info": "•", "warning": "⚠", "critical": "✗"}[self.value]

    @property
    def severity(self) -> int:
        """Numeric severity for --fail-on comparisons (higher = worse)."""
        return {"info": 0, "warning": 1, "critical": 2}[self.value]


@dataclass(frozen=True)
class Finding:
    """One issue spotted by a rule.

    `node` is the offending manifest node (model, source, exposure...).
    `message` is the human-readable description specific to this instance.
    `suggestion` is an optional one-line hint for how to fix it.
    """

    rule_code: str
    severity: Severity
    node: ManifestNode
    message: str
    suggestion: str | None = None


class AuditRule(ABC):
    """Abstract base for all audit rules.

    Subclasses set `code`, `severity`, and `description` as class attributes,
    then implement `check()` returning a list of Findings.
    """

    code: str  # e.g. "AUDIT001"
    severity: Severity  # fixed per rule
    description: str  # short human description

    @abstractmethod
    def check(self, loader: ManifestLoader) -> list[Finding]:
        """Scan the manifest and return findings (empty list if all good)."""

    def make_finding(
        self,
        node: ManifestNode,
        message: str,
        suggestion: str | None = None,
    ) -> Finding:
        """Helper for subclasses — auto-fills code and severity."""
        return Finding(
            rule_code=self.code,
            severity=self.severity,
            node=node,
            message=message,
            suggestion=suggestion,
        )
