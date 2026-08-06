"""
Tests & coverage rules (AUDIT001, AUDIT002).
"""

from __future__ import annotations

from ...lineage_cli.manifest import ManifestLoader
from .base import AuditRule, Finding, Severity


class ModelWithoutTests(AuditRule):
    """AUDIT001 — model has no attached tests at all.

    No tests means no automated coverage of data quality assumptions.
    Even one not_null on a key column is better than nothing.
    """

    code = "AUDIT001"
    severity = Severity.WARNING
    description = "Model has no attached tests"

    def check(self, loader: ManifestLoader) -> list[Finding]:
        findings: list[Finding] = []
        for node in loader.all_nodes().values():
            if node.resource_type != "model":
                continue
            tests = loader.tests_attached_to(node.unique_id)
            if not tests:
                findings.append(
                    self.make_finding(
                        node=node,
                        message=f"Model '{node.name}' has no tests defined",
                        suggestion=(
                            f"Add at least a not_null + unique test on its primary "
                            f"key column in {node.file_path or 'schema.yml'}"
                        ),
                    )
                )
        return findings


class MissingPrimaryKeyTest(AuditRule):
    """AUDIT002 — model has tests, but none on its primary key.

    The "primary key" is the first column declared in the model's
    columns mapping (heuristic shared with `impact` for consistency).
    Critical because PK violations cause silent downstream corruption.
    """

    code = "AUDIT002"
    severity = Severity.CRITICAL
    description = "Model has no unique/not_null test on its primary key"

    def check(self, loader: ManifestLoader) -> list[Finding]:
        findings: list[Finding] = []
        for node in loader.all_nodes().values():
            if node.resource_type != "model":
                continue
            pk = _first_column(loader, node.unique_id)
            if pk is None:
                # No columns declared at all — falls under AUDIT004, not this rule.
                continue
            tests = loader.tests_attached_to(node.unique_id)
            if not tests:
                # Already caught by AUDIT001; don't double-report.
                continue
            expected_uniq = f"unique_{node.name}_{pk}"
            expected_not_null = f"not_null_{node.name}_{pk}"
            if not any(t.name in (expected_uniq, expected_not_null) for t in tests):
                findings.append(
                    self.make_finding(
                        node=node,
                        message=(
                            f"Model '{node.name}' has tests, but none on its "
                            f"primary key column '{pk}'"
                        ),
                        suggestion=(
                            f"Add a 'unique' and 'not_null' test on column '{pk}' "
                            f"in {node.file_path or 'schema.yml'}"
                        ),
                    )
                )
        return findings


def _first_column(loader: ManifestLoader, unique_id: str) -> str | None:
    """Read the first column name from the manifest's `columns` mapping.

    Returns None if no columns are declared. Used as a PK heuristic.
    """
    raw_node = loader._raw.get("nodes", {}).get(unique_id)
    if not raw_node:
        return None
    columns = raw_node.get("columns")
    if not columns:
        return None
    return next(iter(columns), None)
