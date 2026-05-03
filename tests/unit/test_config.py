"""Tests for the Pydantic configuration schema."""
from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from pydantic import ValidationError

from dbt_forge_cli.config import ForgeConfig


def _validate(model_dict):
    return ForgeConfig.model_validate({"version": 1, "models": [model_dict]})


# ---------------------------------------------------------------------------
# Source XOR
# ---------------------------------------------------------------------------


def test_source_or_source_model_required():
    with pytest.raises(ValidationError, match="exactly one of"):
        _validate({"name": "x", "select_columns": ["*"]})


def test_both_source_and_source_model_rejected():
    with pytest.raises(ValidationError, match="exactly one of"):
        _validate({
            "name": "x",
            "source": "a.b",
            "source_model": "y",
            "select_columns": ["*"],
        })


def test_source_format_enforced():
    with pytest.raises(ValidationError, match=r"schema\.table"):
        _validate({"name": "x", "source": "no_dot", "select_columns": ["*"]})
    with pytest.raises(ValidationError, match=r"schema\.table"):
        _validate({"name": "x", "source": "too.many.dots", "select_columns": ["*"]})


# ---------------------------------------------------------------------------
# Identifier hygiene
# ---------------------------------------------------------------------------


def test_name_must_be_identifier():
    with pytest.raises(ValidationError):
        _validate({"name": "1bad", "source": "a.b", "select_columns": ["*"]})
    with pytest.raises(ValidationError):
        _validate({"name": "with space", "source": "a.b", "select_columns": ["*"]})


# ---------------------------------------------------------------------------
# Filter operator/value coherence
# ---------------------------------------------------------------------------


def test_in_requires_list():
    with pytest.raises(ValidationError, match="requires a list"):
        _validate({
            "name": "x",
            "source": "a.b",
            "filters": [{"column": "c", "op": "in", "value": "single"}],
        })


def test_is_null_rejects_value():
    with pytest.raises(ValidationError, match="must not have a value"):
        _validate({
            "name": "x",
            "source": "a.b",
            "filters": [{"column": "c", "op": "is null", "value": 42}],
        })


# ---------------------------------------------------------------------------
# Threshold ↔ metric reference
# ---------------------------------------------------------------------------


def test_threshold_must_reference_existing_metric():
    with pytest.raises(ValidationError, match="unknown metric"):
        _validate({
            "name": "x",
            "source": "a.b",
            "metrics": [{"name": "rev", "based_on": "amount", "operation": "sum"}],
            "breakdown_by": ["c"],
            "thresholds": [{"metric": "ghost", "op": ">", "value": 1}],
        })


def test_threshold_with_known_metric_ok():
    cfg = _validate({
        "name": "x",
        "source": "a.b",
        "select_columns": ["c"],
        "metrics": [{"name": "rev", "based_on": "amount", "operation": "sum"}],
        "breakdown_by": ["c"],
        "thresholds": [{"metric": "rev", "op": ">", "value": 1}],
    })
    assert cfg.models[0].thresholds[0].metric == "rev"


# ---------------------------------------------------------------------------
# Sort references
# ---------------------------------------------------------------------------


def test_sort_must_reference_known_metric_or_column():
    with pytest.raises(ValidationError, match="unknown metric"):
        _validate({
            "name": "x",
            "source": "a.b",
            "select_columns": ["c"],
            "sort_by": [{"metric": "ghost", "order": "desc"}],
        })

    with pytest.raises(ValidationError, match="unknown column"):
        _validate({
            "name": "x",
            "source": "a.b",
            "select_columns": ["c"],
            "sort_by": [{"column": "ghost", "order": "asc"}],
        })


def test_sort_item_requires_exactly_one_target():
    with pytest.raises(ValidationError, match="exactly one of"):
        _validate({
            "name": "x",
            "source": "a.b",
            "sort_by": [{"metric": "rev", "column": "c", "order": "asc"}],
        })


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


def test_duplicate_model_names_rejected():
    with pytest.raises(ValidationError, match="Duplicate"):
        ForgeConfig.model_validate({
            "version": 1,
            "models": [
                {"name": "x", "source": "a.b", "select_columns": ["*"]},
                {"name": "x", "source": "a.c", "select_columns": ["*"]},
            ],
        })
