"""
Cross-model business rules that go beyond per-model Pydantic validation.

Per-model checks live in `config.py` (model_validator). Anything requiring the
whole config (e.g. detecting a `columns_meta` entry referencing a column not in
`select_columns`) lives here.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import ForgeConfig


@dataclass(frozen=True)
class BusinessRuleError:
    model: str
    code: str
    message: str


def check_columns_meta_alignment(cfg: ForgeConfig) -> list[BusinessRuleError]:
    """columns_meta should only describe columns the model actually exposes.

    With wildcard select_columns we cannot know the schema statically, so we skip.
    """
    errors: list[BusinessRuleError] = []
    for m in cfg.models:
        if "*" in m.select_columns:
            continue
        exposed = set(m.select_columns) | {met.name for met in m.metrics}
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
