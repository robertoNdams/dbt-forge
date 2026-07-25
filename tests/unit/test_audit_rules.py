"""
Tests for each audit rule against the fixture manifest.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dbt_forge_cli.audit_cli.rules import (
    DeadModels,
    InconsistentMaterialization,
    MissingColumnDescriptions,
    MissingModelDescription,
    MissingPrimaryKeyTest,
    ModelWithoutTests,
    OrphanSources,
    UndocumentedExposureDependencies,
)
from dbt_forge_cli.audit_cli.rules.base import Severity
from dbt_forge_cli.lineage_cli.manifest import ManifestLoader

FIXTURE = Path(__file__).parent / "fixtures" / "manifest_audit.json"


@pytest.fixture(scope="module")
def loader() -> ManifestLoader:
    return ManifestLoader.from_path(FIXTURE)


def _names(findings):
    return sorted(f.node.name for f in findings)


# ---------------------------------------------------------------------------
# AUDIT001 — ModelWithoutTests
# ---------------------------------------------------------------------------


def test_audit001_flags_models_without_tests(loader):
    rule = ModelWithoutTests()
    findings = rule.check(loader)
    # stg_clean and stg_no_pk_test have tests; everything else doesn't
    assert "stg_clean" not in _names(findings)
    assert "stg_no_pk_test" not in _names(findings)
    # stg_no_tests is the headline case
    assert "stg_no_tests" in _names(findings)
    assert "stg_no_description" in _names(findings)
    assert "dead_model" in _names(findings)


def test_audit001_severity(loader):
    rule = ModelWithoutTests()
    for f in rule.check(loader):
        assert f.severity == Severity.WARNING
        assert f.rule_code == "AUDIT001"


# ---------------------------------------------------------------------------
# AUDIT002 — MissingPrimaryKeyTest
# ---------------------------------------------------------------------------


def test_audit002_flags_model_with_tests_but_no_pk_test(loader):
    rule = MissingPrimaryKeyTest()
    findings = rule.check(loader)
    # stg_no_pk_test has a not_null on 'amount' but the PK is 'id' -> CRITICAL
    assert "stg_no_pk_test" in _names(findings)
    # stg_clean has unique + not_null on 'id' -> OK
    assert "stg_clean" not in _names(findings)
    # Models without ANY tests are not flagged here (AUDIT001 covers them)
    assert "stg_no_tests" not in _names(findings)


def test_audit002_severity(loader):
    rule = MissingPrimaryKeyTest()
    findings = rule.check(loader)
    assert all(f.severity == Severity.CRITICAL for f in findings)


# ---------------------------------------------------------------------------
# AUDIT003 — MissingModelDescription
# ---------------------------------------------------------------------------


def test_audit003_flags_models_without_description(loader):
    rule = MissingModelDescription()
    findings = rule.check(loader)
    assert "stg_no_description" in _names(findings)
    assert "exposed_undocumented" in _names(findings)
    # Models with description shouldn't be flagged
    assert "stg_clean" not in _names(findings)


def test_audit003_severity_is_info(loader):
    rule = MissingModelDescription()
    for f in rule.check(loader):
        assert f.severity == Severity.INFO


# ---------------------------------------------------------------------------
# AUDIT004 — MissingColumnDescriptions
# ---------------------------------------------------------------------------


def test_audit004_flags_model_with_undocumented_columns(loader):
    rule = MissingColumnDescriptions()
    findings = rule.check(loader)
    # stg_undocumented_cols has 'id' and 'a' undocumented, 'b' documented
    assert "stg_undocumented_cols" in _names(findings)
    # Find the specific finding and check the message
    finding = next(f for f in findings if f.node.name == "stg_undocumented_cols")
    assert "2/3" in finding.message  # 2 of 3 columns missing


def test_audit004_does_not_flag_fully_documented(loader):
    rule = MissingColumnDescriptions()
    names = _names(rule.check(loader))
    # stg_clean: all columns documented -> not flagged
    assert "stg_clean" not in names


# ---------------------------------------------------------------------------
# AUDIT005 — OrphanSources
# ---------------------------------------------------------------------------


def test_audit005_flags_unused_source(loader):
    rule = OrphanSources()
    findings = rule.check(loader)
    assert _names(findings) == ["orphan_table"]


def test_audit005_severity(loader):
    rule = OrphanSources()
    for f in rule.check(loader):
        assert f.severity == Severity.WARNING


# ---------------------------------------------------------------------------
# AUDIT006 — InconsistentMaterialization
# ---------------------------------------------------------------------------


def test_audit006_flags_hot_view(loader):
    rule = InconsistentMaterialization()
    findings = rule.check(loader)
    # stg_hot_view is a view with 5 downstream marts -> flagged
    assert "stg_hot_view" in _names(findings)
    # stg_clean is a view but no downstream models -> not flagged
    assert "stg_clean" not in _names(findings)


def test_audit006_count_in_message(loader):
    rule = InconsistentMaterialization()
    findings = rule.check(loader)
    finding = next(f for f in findings if f.node.name == "stg_hot_view")
    assert "5 downstream models" in finding.message


# ---------------------------------------------------------------------------
# AUDIT007 — DeadModels
# ---------------------------------------------------------------------------


def test_audit007_flags_dead_model(loader):
    rule = DeadModels()
    findings = rule.check(loader)
    assert "dead_model" in _names(findings)


def test_audit007_does_not_flag_modeling_consumed_by_exposure(loader):
    rule = DeadModels()
    names = _names(rule.check(loader))
    # exposed_undocumented feeds an exposure -> not dead
    assert "exposed_undocumented" not in names
    # stg_clean feeds an exposure too
    assert "stg_clean" not in names


def test_audit007_does_not_flag_intermediate_model(loader):
    rule = DeadModels()
    names = _names(rule.check(loader))
    # stg_hot_view feeds 5 marts — alive
    assert "stg_hot_view" not in names


# ---------------------------------------------------------------------------
# AUDIT008 — UndocumentedExposureDependencies
# ---------------------------------------------------------------------------


def test_audit008_flags_exposure_with_undocumented_parent(loader):
    rule = UndocumentedExposureDependencies()
    findings = rule.check(loader)
    # dashboard_clean depends on stg_clean (documented) and
    # exposed_undocumented (not). Should be flagged.
    assert _names(findings) == ["dashboard_clean"]
    finding = findings[0]
    assert "exposed_undocumented" in finding.message


def test_audit008_severity(loader):
    rule = UndocumentedExposureDependencies()
    for f in rule.check(loader):
        assert f.severity == Severity.WARNING


# ---------------------------------------------------------------------------
# Stability: every rule has a stable code / severity / description
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule_cls,expected_code,expected_severity",
    [
        (ModelWithoutTests, "AUDIT001", Severity.WARNING),
        (MissingPrimaryKeyTest, "AUDIT002", Severity.CRITICAL),
        (MissingModelDescription, "AUDIT003", Severity.INFO),
        (MissingColumnDescriptions, "AUDIT004", Severity.INFO),
        (OrphanSources, "AUDIT005", Severity.WARNING),
        (InconsistentMaterialization, "AUDIT006", Severity.WARNING),
        (DeadModels, "AUDIT007", Severity.INFO),
        (UndocumentedExposureDependencies, "AUDIT008", Severity.WARNING),
    ],
)
def test_rule_metadata(rule_cls, expected_code, expected_severity):
    instance = rule_cls()
    assert instance.code == expected_code
    assert instance.severity == expected_severity
    assert instance.description  # not empty
