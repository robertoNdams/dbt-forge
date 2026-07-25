"""
JSON renderer for the audit report — for CI orchestration, jq pipelines,
GitHub Action annotations, etc.
"""

from __future__ import annotations

import json

from ..engine import AuditReport
from ..rules.base import Finding, Severity


def render_audit_json(report: AuditReport) -> str:
    """Return a pretty-printed JSON string representing the audit report."""
    by_sev = report.by_severity
    payload = {
        "rules_run": report.rules_run,
        "models_scanned": report.total_models_scanned,
        "findings_count": len(report.findings),
        "findings": [_finding_payload(f) for f in report.findings],
        "summary": {
            "by_severity": {
                sev.value: len(items) for sev, items in by_sev.items()
            },
            "models_affected": len({f.node.unique_id for f in report.findings}),
            "max_severity": (
                report.max_severity.value if report.max_severity else None
            ),
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def _finding_payload(f: Finding) -> dict:
    return {
        "rule": f.rule_code,
        "severity": f.severity.value,
        "node": {
            "name": f.node.name,
            "unique_id": f.node.unique_id,
            "resource_type": f.node.resource_type,
            "file_path": f.node.file_path,
        },
        "message": f.message,
        "suggestion": f.suggestion,
    }
