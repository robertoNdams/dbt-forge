"""Macro-render tests using the Jinja harness."""

from __future__ import annotations

import pytest

# `jinja_harness` is made importable by the root conftest.py
from jinja_harness import build  # type: ignore


@pytest.fixture(scope="module")
def h():
    return build()


def _basecfg(**overrides):
    base = {
        "name": "test_model",
        "source": "raw.t",
        "select_columns": ["*"],
        "filters": [],
        "metrics": [],
        "breakdown_by": [],
        "thresholds": [],
        "sort_by": [],
        "include_sources": [],
    }
    base.update(overrides)
    return base


def test_base_select_with_source(h):
    out = h.call("render_base_select", _basecfg())
    assert "select" in out
    assert "from {{ source('raw', 't') }}" in out


def test_base_select_with_source_model(h):
    cfg = _basecfg()
    cfg.pop("source")
    cfg["source_model"] = "stg_orders"
    out = h.call("render_base_select", cfg)
    assert "from {{ ref('stg_orders') }}" in out


def test_distinct_select(h):
    out = h.call("render_distinct_select", _basecfg(select_columns=["a", "b"]))
    assert out.startswith("select distinct\n")


def test_filtered_select_no_filters_passthrough(h):
    cfg = _basecfg()
    out = h.call("render_filtered_select", cfg)
    assert "where" not in out


def test_filtered_select_combines_clauses(h):
    cfg = _basecfg(
        filters=[
            {"column": "status", "op": "!=", "value": "x"},
            {"column": "amount", "op": ">", "value": 0},
        ]
    )
    out = h.call("render_filtered_select", cfg)
    assert "where status != 'x'" in out
    assert "and amount > 0" in out


def test_in_filter_renders_parens(h):
    cfg = _basecfg(filters=[{"column": "c", "op": "in", "value": ["a", "b"]}])
    out = h.call("render_filtered_select", cfg)
    assert "c in ('a', 'b')" in out


def test_is_null_filter(h):
    cfg = _basecfg(filters=[{"column": "deleted_at", "op": "is null", "value": None}])
    out = h.call("render_filtered_select", cfg)
    assert "deleted_at is null" in out


def test_aggregation_select_emits_group_by(h):
    cfg = _basecfg(
        select_columns=["customer_id"],
        metrics=[{"name": "rev", "based_on": "amount", "operation": "sum"}],
        breakdown_by=["customer_id"],
    )
    out = h.call("render_aggregation_select", cfg)
    assert "sum(amount) as rev" in out
    assert "group by customer_id" in out


def test_count_distinct_metric(h):
    cfg = _basecfg(
        metrics=[{"name": "n", "based_on": "id", "operation": "count_distinct"}],
        breakdown_by=["x"],
    )
    out = h.call("render_aggregation_select", cfg)
    assert "count(distinct id) as n" in out


def test_thresholds_select(h):
    cfg = _basecfg(
        metrics=[{"name": "rev", "based_on": "amount", "operation": "sum"}],
        breakdown_by=["c"],
        thresholds=[{"metric": "rev", "op": ">", "value": 100}],
    )
    out = h.call("render_thresholds_select", cfg)
    assert "having rev > 100" in out


def test_sorted_select_for_aggregation(h):
    cfg = _basecfg(
        metrics=[{"name": "rev", "based_on": "amount", "operation": "sum"}],
        breakdown_by=["c"],
        sort_by=[{"metric": "rev", "order": "desc"}],
    )
    out = h.call("render_sorted_select", cfg)
    assert "order by" in out
    assert "rev desc" in out


def test_sorted_select_for_simple_select(h):
    cfg = _basecfg(
        select_columns=["id", "name"],
        sort_by=[{"column": "id", "order": "asc"}],
    )
    out = h.call("render_sorted_select", cfg)
    assert "order by" in out
    assert "id asc" in out


def test_full_select_aliases_sorted(h):
    cfg = _basecfg(select_columns=["a"], sort_by=[{"column": "a", "order": "desc"}])
    a = h.call("render_full_select", cfg)
    b = h.call("render_sorted_select", cfg)
    assert a == b


def test_ctes_select_emits_with_clause_and_uses_cte_name(h):
    cfg = _basecfg(
        source_model="paid",  # references the CTE
        metrics=[{"name": "tot", "based_on": "amount", "operation": "sum"}],
        breakdown_by=["customer_id"],
        thresholds=[{"metric": "tot", "op": ">", "value": 500}],
        template="full_select",
        include_sources=[
            {
                "name": "paid",
                "source_model": "stg_orders",
                "template": "filtered_select",
                "select_columns": ["customer_id", "amount"],
                "filters": [{"column": "status", "op": "=", "value": "paid"}],
            }
        ],
    )
    cfg.pop("source")
    out = h.call("render_ctes_select", cfg)
    assert out.startswith("with\npaid as (")
    assert "from paid" in out  # main select reads from the CTE
    assert "from {{ ref('stg_orders') }}" in out  # CTE reads from the upstream
    assert "having tot > 500" in out


def test_schema_yml_basic(h):
    yml = h.call(
        "build_schema_yml",
        [
            {
                "name": "stg",
                "description": "x",
                "columns_meta": [
                    {"name": "id", "tests": ["not_null", "unique"]},
                ],
            }
        ],
    )
    assert "version: 2" in yml
    assert "- name: stg" in yml
    assert "- not_null" in yml
    assert "- unique" in yml


# ---------------------------------------------------------------------------
# Dispatch contract regression tests
# ---------------------------------------------------------------------------


def test_no_double_default_prefix_in_dispatch_calls():
    """
    History: an earlier version of the macros called
        adapter.dispatch('default__render_X', 'dbt_forge')
    which dbt resolves as `default__default__render_X` — and fails. This
    test grep-locks the macros against re-introduction of that pattern.
    """
    from pathlib import Path

    macros_root = Path(__file__).resolve().parents[2] / "dbt" / "dbt_forge" / "macros"
    bad: list[tuple[str, int, str]] = []
    for path in macros_root.rglob("*.sql"):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if "adapter.dispatch('default__" in line or 'adapter.dispatch("default__' in line:
                bad.append((str(path), lineno, line.strip()))
    assert not bad, (
        "adapter.dispatch must be called with the bare macro name "
        "(e.g. 'render_full_select'), not 'default__render_full_select'. "
        "Offending lines:\n" + "\n".join(f"  {p}:{n}: {line_text}" for p, n, line_text in bad)
    )


def test_no_dynamic_dispatch_in_macros():
    """
    dbt's static parser (statically_parse_adapter_dispatch) expects the first
    argument to adapter.dispatch(...) to be a string literal. A runtime
    expression like adapter.dispatch('render_' ~ name, ...) raises:

        AttributeError: 'Concat' object has no attribute 'value'

    at `dbt parse` time. Use `dbt_forge.dispatch_template(name, cfg)` instead,
    which fans out to literal-string dispatch calls.

    We scan only inside `{% macro %}` bodies — `adapter.dispatch(...)` mentions
    in doc-comments outside macros are not real calls.
    """
    import re
    from pathlib import Path

    macros_root = Path(__file__).resolve().parents[2] / "dbt" / "dbt_forge" / "macros"
    macro_open = re.compile(r"\{%-?\s*macro\b")
    macro_close = re.compile(r"\{%-?\s*endmacro\b")

    bad: list[tuple[str, int, str]] = []
    for path in macros_root.rglob("*.sql"):
        inside_macro = False
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if macro_open.search(line):
                inside_macro = True
            if not inside_macro:
                continue
            if "adapter.dispatch(" in line:
                idx = line.index("adapter.dispatch(") + len("adapter.dispatch(")
                rest = line[idx:].lstrip()
                if not rest or rest[0] not in ("'", '"'):
                    bad.append((str(path), lineno, line.strip()))
            if macro_close.search(line):
                inside_macro = False

    assert not bad, (
        "adapter.dispatch() must be called with a literal string as first "
        "argument (dbt static parser limitation). Use dispatch_template() "
        "for dynamic dispatch. Offending lines:\n"
        + "\n".join(f"  {p}:{n}: {line_text}" for p, n, line_text in bad)
    )
