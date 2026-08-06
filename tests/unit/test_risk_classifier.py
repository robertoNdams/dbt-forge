"""Tests for risk classification (impact analysis)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dbt_forge_cli.lineage_cli.manifest import ManifestLoader
from dbt_forge_cli.lineage_cli.risk import Risk, classify_node

FIXTURE = Path(__file__).parent / "fixtures" / "manifest_sample.json"


@pytest.fixture(scope="module")
def loader() -> ManifestLoader:
    return ManifestLoader.from_path(FIXTURE)


def test_risk_enum_ordering():
    assert Risk.OK.severity < Risk.WARNING.severity < Risk.CRITICAL.severity


def test_risk_icons():
    assert Risk.OK.icon == "✓"
    assert Risk.WARNING.icon == "⚠"
    assert Risk.CRITICAL.icon == "✗"


def test_fct_with_pk_test_is_ok_without_exposure_proximate(loader):
    # fct_revenue_per_customer has a unique test on customer_id (its first column).
    # Its downstream eventually reaches an exposure, so this should still
    # trigger a warning only if no pk test — here it HAS a pk test, so ok.
    node = loader.get("model.jaffle_shop.fct_revenue_per_customer")
    r = classify_node(loader, node, depth=1, exposures_for_root=[])
    # Has pk test on customer_id and downstream exposure exists
    assert r.has_pk_test is True
    assert r.tests_count == 1
    assert len(r.exposures) == 1  # executive_dashboard via rpt_top_customers
    assert r.level == Risk.OK


def test_rpt_without_tests_with_exposure_is_critical(loader):
    # rpt_top_customers has zero tests in the fixture and its downstream
    # contains an exposure -> CRITICAL
    node = loader.get("model.jaffle_shop.rpt_top_customers")
    r = classify_node(loader, node, depth=2, exposures_for_root=[])
    assert r.tests_count == 0
    assert len(r.exposures) == 1
    assert r.level == Risk.CRITICAL


def test_stg_customers_no_tests_no_exposure_is_warning(loader):
    # stg_customers has no attached tests and no downstream exposure
    node = loader.get("model.jaffle_shop.stg_customers")
    r = classify_node(loader, node, depth=1, exposures_for_root=[])
    assert r.tests_count == 0
    assert r.exposures == []
    assert r.level == Risk.WARNING


def test_stg_orders_has_pk_tests_and_downstream_exposure(loader):
    # stg_orders has unique + not_null on order_id (its first column),
    # so has_pk_test True, downstream exposure True -> OK
    node = loader.get("model.jaffle_shop.stg_orders")
    r = classify_node(loader, node, depth=1, exposures_for_root=[])
    assert r.tests_count == 2
    assert r.has_pk_test is True
    assert len(r.exposures) == 1
    assert r.level == Risk.OK


def test_reasons_for_warning(loader):
    node = loader.get("model.jaffle_shop.stg_customers")
    r = classify_node(loader, node, depth=1, exposures_for_root=[])
    assert "no tests" in r.reasons


def test_reasons_for_critical(loader):
    node = loader.get("model.jaffle_shop.rpt_top_customers")
    r = classify_node(loader, node, depth=2, exposures_for_root=[])
    reasons = r.reasons
    assert "no tests" in reasons
    assert any("exposure" in r for r in reasons)
