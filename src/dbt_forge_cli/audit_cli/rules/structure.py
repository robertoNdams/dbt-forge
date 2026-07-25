"""
Structure & configuration rules (AUDIT005, AUDIT006, AUDIT007, AUDIT008).
"""

from __future__ import annotations

from ...lineage_cli.manifest import ManifestLoader
from .base import AuditRule, Finding, Severity


class OrphanSources(AuditRule):
    """AUDIT005 — source declared but never referenced by any model.

    Orphan sources are dead config: they document data that nothing
    consumes, which is misleading for new team members exploring the
    project and inflates `dbt parse` time.
    """

    code = "AUDIT005"
    severity = Severity.WARNING
    description = "Source is declared but never referenced"

    def check(self, loader: ManifestLoader) -> list[Finding]:
        findings: list[Finding] = []
        for node in loader.all_nodes().values():
            if node.resource_type != "source":
                continue
            consumers = loader.children_of(node.unique_id)
            if not consumers:
                findings.append(
                    self.make_finding(
                        node=node,
                        message=(
                            f"Source '{node.schema}.{node.name}' is declared "
                            f"but no model references it"
                        ),
                        suggestion=(
                            f"Either reference it via {{{{ source('{node.schema}', "
                            f"'{node.name}') }}}}, or remove it from "
                            f"{node.file_path or 'sources.yml'}"
                        ),
                    )
                )
        return findings


class InconsistentMaterialization(AuditRule):
    """AUDIT006 — model materialized as `view` but consumed by many marts.

    A view consumed by many marts re-executes its SQL on every downstream
    query. If consumed by 5+ downstream models that all run regularly,
    you're paying that compute multiple times — `table` or `incremental`
    is probably a better fit.

    The threshold (5) is hard-coded for V1. Configurable in V2 via
    .dbt-forge.yml.
    """

    code = "AUDIT006"
    severity = Severity.WARNING
    description = (
        "Model materialized as 'view' but consumed by 5+ downstream models"
    )
    DOWNSTREAM_THRESHOLD = 5

    def check(self, loader: ManifestLoader) -> list[Finding]:
        findings: list[Finding] = []
        for node in loader.all_nodes().values():
            if node.resource_type != "model":
                continue
            raw = loader._raw.get("nodes", {}).get(node.unique_id, {})
            config = raw.get("config", {}) or {}
            materialized = (config.get("materialized") or "view").lower()
            if materialized != "view":
                continue
            # Count downstream MODELS (not tests, not exposures, not analyses)
            downstream_models = sum(
                1
                for child_uid in loader.children_of(node.unique_id)
                for child in [loader.get(child_uid)]
                if child is not None and child.resource_type == "model"
            )
            if downstream_models >= self.DOWNSTREAM_THRESHOLD:
                findings.append(
                    self.make_finding(
                        node=node,
                        message=(
                            f"Model '{node.name}' is a view consumed by "
                            f"{downstream_models} downstream models — every "
                            f"downstream query re-executes its SQL"
                        ),
                        suggestion=(
                            f"Consider switching to materialized='table' or "
                            f"'incremental' in {node.file_path or 'the model config'}"
                        ),
                    )
                )
        return findings


class DeadModels(AuditRule):
    """AUDIT007 — model is never referenced and never exposed.

    Dead models are project debt: they still run during builds, still
    appear in dbt docs, still confuse newcomers. If nothing consumes them
    (no downstream model, no exposure), they should be removed or marked
    as exposures themselves.
    """

    code = "AUDIT007"
    severity = Severity.INFO
    description = "Model is never referenced and never feeds an exposure"

    def check(self, loader: ManifestLoader) -> list[Finding]:
        findings: list[Finding] = []
        for node in loader.all_nodes().values():
            if node.resource_type != "model":
                continue
            children = loader.children_of(node.unique_id)
            # A model is "alive" if at least one child is a model or exposure
            alive = any(
                (child := loader.get(child_uid)) is not None
                and child.resource_type in ("model", "exposure")
                for child_uid in children
            )
            if not alive:
                findings.append(
                    self.make_finding(
                        node=node,
                        message=(
                            f"Model '{node.name}' is never referenced and feeds "
                            f"no exposure — potential dead code"
                        ),
                        suggestion=(
                            f"Either remove {node.file_path}, declare it as an "
                            f"exposure, or mark it as a public entry point"
                        ),
                    )
                )
        return findings


class UndocumentedExposureDependencies(AuditRule):
    """AUDIT008 — exposure depends on undocumented models.

    Exposures are the contracts between dbt and the outside world (BI
    dashboards, ML models, public APIs). If a dashboard depends on a
    model that has no description, the consumer can't understand what
    they're reading without asking the data team.
    """

    code = "AUDIT008"
    severity = Severity.WARNING
    description = "Exposure depends on undocumented models"

    def check(self, loader: ManifestLoader) -> list[Finding]:
        findings: list[Finding] = []
        for node in loader.all_nodes().values():
            if node.resource_type != "exposure":
                continue
            parents = loader.parents_of(node.unique_id)
            undocumented: list[str] = []
            for parent_uid in parents:
                parent = loader.get(parent_uid)
                if parent is None or parent.resource_type != "model":
                    continue
                raw = loader._raw.get("nodes", {}).get(parent_uid, {})
                if not (raw.get("description") or "").strip():
                    undocumented.append(parent.name)
            if undocumented:
                preview = ", ".join(undocumented[:3])
                if len(undocumented) > 3:
                    preview += f", +{len(undocumented) - 3} more"
                findings.append(
                    self.make_finding(
                        node=node,
                        message=(
                            f"Exposure '{node.name}' depends on {len(undocumented)} "
                            f"undocumented model(s): {preview}"
                        ),
                        suggestion=(
                            f"Document those models so consumers of '{node.name}' "
                            f"understand the data they're using"
                        ),
                    )
                )
        return findings
