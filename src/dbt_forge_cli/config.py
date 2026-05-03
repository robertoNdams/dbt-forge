"""
Pydantic schemas for the dbt-forge YAML DSL.

These mirror the manifest section 3 (DSL) and are the single source of truth
for configuration validation. Errors raised here surface as structured errors
in the CLI before any dbt invocation.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


class Operator(str, Enum):
    EQ = "="
    NEQ = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    IN = "in"
    NOT_IN = "not in"
    LIKE = "like"
    IS_NULL = "is null"
    IS_NOT_NULL = "is not null"


class Aggregation(str, Enum):
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class OutputType(str, Enum):
    VIEW = "view"
    TABLE = "table"
    INCREMENTAL = "incremental"


# ---------------------------------------------------------------------------
# Leaf objects
# ---------------------------------------------------------------------------


class Filter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    op: Operator
    value: str | int | float | bool | list | None = None

    @model_validator(mode="after")
    def _check_value_for_op(self) -> Filter:
        if self.op in {Operator.IS_NULL, Operator.IS_NOT_NULL} and self.value is not None:
            raise ValueError(f"Operator '{self.op.value}' must not have a value.")
        if self.op in {Operator.IN, Operator.NOT_IN} and not isinstance(self.value, list):
            raise ValueError(f"Operator '{self.op.value}' requires a list value.")
        return self


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    based_on: str = Field(..., min_length=1)
    operation: Aggregation


class Threshold(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    op: Operator
    value: int | float


class SortItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str | None = None
    column: str | None = None
    order: SortOrder = SortOrder.ASC

    @model_validator(mode="after")
    def _exactly_one(self) -> SortItem:
        if (self.metric is None) == (self.column is None):
            raise ValueError("sort item must have exactly one of `metric` or `column`.")
        return self


class ColumnMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    tests: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Nested CTE (forward-declared via string ref)
# ---------------------------------------------------------------------------


class IncludedSource(BaseModel):
    """A nested CTE inlined into a parent model."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str | None = None
    source_model: str | None = None
    template: str = "base_select"
    select_columns: list[str] = Field(default_factory=lambda: ["*"])
    filters: list[Filter] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_source(self) -> IncludedSource:
        if (self.source is None) == (self.source_model is None):
            raise ValueError(
                f"Included source '{self.name}' must define exactly one of "
                "`source` or `source_model`."
            )
        return self


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1)]
    description: str | None = None

    # Source — exactly one required
    source: str | None = None
    source_model: str | None = None

    # Template
    template: str = "full_select"

    # SELECT
    select_columns: list[str] = Field(default_factory=lambda: ["*"])
    distinct: bool = False

    # Transformations
    filters: list[Filter] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    breakdown_by: list[str] = Field(default_factory=list)
    thresholds: list[Threshold] = Field(default_factory=list)
    sort_by: list[SortItem] = Field(default_factory=list)

    # Advanced
    include_sources: list[IncludedSource] = Field(default_factory=list)

    # Materialization
    output_type: OutputType = OutputType.VIEW

    # Schema metadata
    columns_meta: list[ColumnMeta] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Cross-field business rules
    # ------------------------------------------------------------------

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, v: str) -> str:
        if not v.replace("_", "").isalnum():
            raise ValueError(
                f"Model name '{v}' must contain only alphanumerics and underscores."
            )
        if v[0].isdigit():
            raise ValueError(f"Model name '{v}' must not start with a digit.")
        return v

    @field_validator("source")
    @classmethod
    def _source_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v.count(".") != 1 or any(part == "" for part in v.split(".")):
            raise ValueError(
                f"`source` must be of the form 'schema.table' (got '{v}')."
            )
        return v

    @model_validator(mode="after")
    def _exactly_one_source(self) -> ModelConfig:
        if (self.source is None) == (self.source_model is None):
            raise ValueError(
                f"Model '{self.name}' must define exactly one of "
                "`source` or `source_model`."
            )
        return self

    @model_validator(mode="after")
    def _thresholds_reference_known_metrics(self) -> ModelConfig:
        known = {m.name for m in self.metrics}
        for t in self.thresholds:
            if t.metric not in known:
                raise ValueError(
                    f"Model '{self.name}': threshold references unknown metric "
                    f"'{t.metric}'. Known metrics: {sorted(known) or '∅'}."
                )
        return self

    @model_validator(mode="after")
    def _sort_references_known(self) -> ModelConfig:
        known_metrics = {m.name for m in self.metrics}
        known_columns = set(self.select_columns) | set(self.breakdown_by)
        for s in self.sort_by:
            if s.metric and s.metric not in known_metrics:
                raise ValueError(
                    f"Model '{self.name}': sort_by references unknown metric "
                    f"'{s.metric}'."
                )
            if (
                s.column
                and "*" not in known_columns
                and s.column not in known_columns
            ):
                raise ValueError(
                    f"Model '{self.name}': sort_by references unknown column "
                    f"'{s.column}'."
                )
        return self


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


class ForgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    models: list[ModelConfig]

    @model_validator(mode="after")
    def _unique_names(self) -> ForgeConfig:
        seen: set[str] = set()
        for m in self.models:
            if m.name in seen:
                raise ValueError(f"Duplicate model name: '{m.name}'.")
            seen.add(m.name)
        return self
