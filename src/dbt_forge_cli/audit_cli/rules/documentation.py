"""
Documentation rules (AUDIT003, AUDIT004).
"""

from __future__ import annotations

from ...lineage_cli.manifest import ManifestLoader
from .base import AuditRule, Finding, Severity


class MissingModelDescription(AuditRule):
    """AUDIT003 — model has no description.

    Undocumented models become tribal knowledge. New team members and
    LLM-based agents struggle to use them effectively.
    """

    code = "AUDIT003"
    severity = Severity.INFO
    description = "Model has no description"

    def check(self, loader: ManifestLoader) -> list[Finding]:
        findings: list[Finding] = []
        for node in loader.all_nodes().values():
            if node.resource_type != "model":
                continue
            raw = loader._raw.get("nodes", {}).get(node.unique_id, {})
            description = (raw.get("description") or "").strip()
            if not description:
                findings.append(
                    self.make_finding(
                        node=node,
                        message=f"Model '{node.name}' has no description",
                        suggestion=(
                            f"Add a 'description:' field for '{node.name}' in "
                            f"{node.file_path or 'schema.yml'}"
                        ),
                    )
                )
        return findings


class MissingColumnDescriptions(AuditRule):
    """AUDIT004 — model has columns but they have no descriptions.

    A model with columns: foo: {} (no description) is worse than a model
    with no columns declared at all — it signals an abandoned attempt at
    documentation. Only flagged for models that already have at least one
    column declared (so we don't double-fire with rules that expect columns).
    """

    code = "AUDIT004"
    severity = Severity.INFO
    description = "Model has columns declared but they lack descriptions"

    def check(self, loader: ManifestLoader) -> list[Finding]:
        findings: list[Finding] = []
        for node in loader.all_nodes().values():
            if node.resource_type != "model":
                continue
            raw = loader._raw.get("nodes", {}).get(node.unique_id, {})
            columns = raw.get("columns") or {}
            if not columns:
                continue
            missing = [
                name
                for name, meta in columns.items()
                if not (meta or {}).get("description", "").strip()
            ]
            if not missing:
                continue
            preview = ", ".join(missing[:3])
            if len(missing) > 3:
                preview += f", +{len(missing) - 3} more"
            findings.append(
                self.make_finding(
                    node=node,
                    message=(
                        f"Model '{node.name}': {len(missing)}/{len(columns)} columns "
                        f"have no description ({preview})"
                    ),
                    suggestion=(
                        f"Document the columns in {node.file_path or 'schema.yml'}"
                    ),
                )
            )
        return findings
