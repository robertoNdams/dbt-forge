"""
Cross-model business rules that go beyond per-model Pydantic validation.

Per-model checks live in `config.py` (model_validator). Anything requiring the
whole config (e.g. detecting a `columns_meta` entry referencing a column not in
`select_columns`) lives here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import ForgeConfig

# Match an explicit SQL alias: "<expr> AS <alias>" (case-insensitive, with the
# alias optionally double-quoted). We capture the alias only.
_ALIAS_RE = re.compile(r"\s+as\s+\"?([A-Za-z_][A-Za-z0-9_]*)\"?\s*$", re.IGNORECASE)
# Fallback: when there's no AS clause, the produced column name is the last
# identifier in the expression (e.g. "schema.table.column" -> "column",
# "trim(email)" -> NOT a valid column-name source, see below).
_BARE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _produced_name(select_expr: str) -> str | None:
    """
    Return the column name a SELECT-list expression produces, or None if it
    cannot be determined statically (e.g. a function call without AS).

    Examples:
        "id"                        -> "id"
        "id as customer_id"         -> "customer_id"
        "schema.t.col"              -> "col"
        "trim(email) as email"      -> "email"
        "trim(email)"               -> None (no alias, can't infer)
        "*"                         -> None (handled separately by caller)
    """
    expr = select_expr.strip()
    if not expr or expr == "*":
        return None
    m = _ALIAS_RE.search(expr)
    if m:
        return m.group(1)
    if _BARE_IDENT_RE.match(expr):
        # Bare identifier or qualified name — take the last segment
        return expr.rsplit(".", 1)[-1]
    return None


def _exposed_columns(select_columns: list[str]) -> tuple[set[str], bool]:
    """
    Return (set of statically-knowable produced column names, has_unknown).

    has_unknown is True when at least one expression couldn't be parsed (e.g.
    a function call without AS). In that case the caller should be lenient
    rather than reject every columns_meta entry.
    """
    exposed: set[str] = set()
    has_unknown = False
    for expr in select_columns:
        name = _produced_name(expr)
        if name is None:
            has_unknown = True
        else:
            exposed.add(name)
    return exposed, has_unknown


@dataclass(frozen=True)
class BusinessRuleError:
    model: str
    code: str
    message: str


def check_columns_meta_alignment(cfg: ForgeConfig) -> list[BusinessRuleError]:
    """columns_meta should only describe columns the model actually exposes.

    With wildcard select_columns or any unparseable expression, we skip the
    check rather than produce false positives.
    """
    errors: list[BusinessRuleError] = []
    for m in cfg.models:
        if "*" in m.select_columns:
            continue
        exposed, has_unknown = _exposed_columns(m.select_columns)
        if has_unknown:
            # At least one expression we can't statically parse — be lenient.
            continue
        exposed |= {met.name for met in m.metrics}
        for cm in m.columns_meta:
            if cm.name not in exposed:
                errors.append(
                    BusinessRuleError(
                        model=m.name,
                        code="ORPHAN_COLUMN_META",
                        message=(
                            f"columns_meta entry '{cm.name}' is not produced by "
                            f"the model (exposed: {sorted(exposed)})."
                        ),
                    )
                )
    return errors


def run_all(cfg: ForgeConfig) -> list[BusinessRuleError]:
    return [
        *check_columns_meta_alignment(cfg),
    ]
