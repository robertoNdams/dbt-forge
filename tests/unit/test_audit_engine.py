"""
Tests for AuditEngine: rule selection, severity threshold, fail-on semantics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dbt_forge_cli.audit_cli.engine import AuditEngine
from dbt_forge_cli.audit_cli.rules.base import Severity
from dbt_forge_cli.lineage_cli.manifest import ManifestLoader

FIXTURE = Path(__file__).parent / "fixtures" / "manifest_audit.json"


@pytest.fixture(scope="module")
def loader() -> ManifestLoader:
    return ManifestLoader.from_path(FIXTURE)


def test_engine_runs_all_rules_by_default(loader):
    engine = AuditEngine()
    report = engine.run(loader)
    assert len(report.rules_run) == 8
    assert "AUDIT001" in report.rules_run
    assert "AUDIT008" in report.rules_run


def test_engine_select_subset(loader):
    engine = AuditEngine(select={"AUDIT001", "AUDIT002"})
    report = engine.run(loader)
    assert report.rules_run == ["AUDIT001", "AUDIT002"]
    codes = {f.rule_code for f in report.findings}
    assert codes <= {"AUDIT001", "AUDIT002"}


def test_engine_exclude(loader):
    engine = AuditEngine(exclude={"AUDIT003", "AUDIT004"})
    report = engine.run(loader)
    assert "AUDIT003" not in report.rules_run
    assert "AUDIT004" not in report.rules_run
    codes = {f.rule_code for f in report.findings}
    assert "AUDIT003" not in codes
    assert "AUDIT004" not in codes


def test_engine_severity_threshold_drops_info(loader):
    engine = AuditEngine(severity_threshold=Severity.WARNING)
    report = engine.run(loader)
    assert all(f.severity != Severity.INFO for f in report.findings)


def test_engine_severity_threshold_critical_only(loader):
    engine = AuditEngine(severity_threshold=Severity.CRITICAL)
    report = engine.run(loader)
    assert all(f.severity == Severity.CRITICAL for f in report.findings)
    # We know AUDIT002 fires on stg_no_pk_test in the fixture
    assert any(f.node.name == "stg_no_pk_test" for f in report.findings)


def test_engine_max_severity(loader):
    engine = AuditEngine()
    report = engine.run(loader)
    assert report.max_severity == Severity.CRITICAL


def test_engine_findings_sorted_worst_first(loader):
    engine = AuditEngine()
    report = engine.run(loader)
    severities = [f.severity.severity for f in report.findings]
    assert severities == sorted(severities, reverse=True)


def test_engine_models_scanned_count(loader):
    engine = AuditEngine()
    report = engine.run(loader)
    # 13 models in the fixture
    assert report.total_models_scanned == 13


def test_empty_report_when_no_findings():
    # Engine on a fixture with no issues
    fake_raw = {
        "nodes": {
            "model.x.ok_model": {
                "name": "ok_model",
                "resource_type": "model",
                "package_name": "x",
                "schema": "main",
                "description": "OK",
                "original_file_path": "models/ok.sql",
                "config": {"materialized": "table"},
                "columns": {"id": {"description": "PK"}},
            }
        },
        "sources": {},
        "exposures": {},
        "parent_map": {"model.x.ok_model": []},
        "child_map": {"model.x.ok_model": []},
    }
    loader = ManifestLoader(fake_raw)
    engine = AuditEngine(exclude={"AUDIT001", "AUDIT002", "AUDIT007"})
    # We exclude rules that would fire on this minimal fixture; the rest pass
    report = engine.run(loader)
    assert report.findings == []
    assert report.max_severity is None
