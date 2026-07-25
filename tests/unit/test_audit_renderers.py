"""
Tests for the audit renderers (ASCII + JSON).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console

from dbt_forge_cli.audit_cli.engine import AuditEngine
from dbt_forge_cli.audit_cli.renderers import (
    render_audit_ascii,
    render_audit_json,
)
from dbt_forge_cli.lineage_cli.manifest import ManifestLoader

FIXTURE = Path(__file__).parent / "fixtures" / "manifest_audit.json"


@pytest.fixture(scope="module")
def report():
    loader = ManifestLoader.from_path(FIXTURE)
    return AuditEngine().run(loader)


@pytest.fixture
def console():
    return Console(record=True, width=120, force_terminal=False, no_color=True)


# ---------------------------------------------------------------------------
# ASCII
# ---------------------------------------------------------------------------


def test_ascii_groups_by_severity(report, console):
    render_audit_ascii(console, report)
    out = console.export_text()
    assert "CRITICAL" in out
    assert "WARNING" in out
    assert "INFO" in out


def test_ascii_includes_rule_codes(report, console):
    render_audit_ascii(console, report)
    out = console.export_text()
    assert "AUDIT001" in out
    assert "AUDIT002" in out


def test_ascii_includes_suggestions(report, console):
    render_audit_ascii(console, report)
    out = console.export_text()
    # All findings have suggestions in our impl
    assert "→" in out


def test_ascii_includes_summary(report, console):
    render_audit_ascii(console, report)
    out = console.export_text()
    assert "Summary" in out
    assert "critical" in out.lower()


def test_ascii_empty_report(console):
    from dbt_forge_cli.audit_cli.engine import AuditReport
    empty = AuditReport(rules_run=["AUDIT001"], total_models_scanned=3)
    render_audit_ascii(console, empty)
    out = console.export_text()
    assert "No issues" in out


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def test_json_well_formed(report):
    out = render_audit_json(report)
    payload = json.loads(out)
    assert "findings" in payload
    assert "summary" in payload
    assert payload["summary"]["max_severity"] == "critical"


def test_json_includes_all_finding_fields(report):
    payload = json.loads(render_audit_json(report))
    f = payload["findings"][0]
    assert "rule" in f
    assert "severity" in f
    assert "node" in f
    assert "message" in f
    assert "suggestion" in f


def test_json_summary_counts_match(report):
    payload = json.loads(render_audit_json(report))
    by_sev = payload["summary"]["by_severity"]
    total = by_sev["critical"] + by_sev["warning"] + by_sev["info"]
    assert total == payload["findings_count"]


def test_json_models_scanned_present(report):
    payload = json.loads(render_audit_json(report))
    assert payload["models_scanned"] == 13
