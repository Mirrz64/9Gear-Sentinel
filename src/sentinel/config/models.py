"""Pydantic models describing sentinel.yml."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sentinel.utils.durations import parse_duration

Severity = Literal["warn", "error"]


class StrictModel(BaseModel):
    """Base model that rejects unknown keys, so typos surface as errors."""

    model_config = ConfigDict(extra="forbid")


# --- sources, store, alerts, schedule -------------------------------------


class Source(StrictModel):
    type: Literal["postgres", "snowflake", "bigquery", "sqlite"]
    url: str = Field(min_length=1)


class Store(StrictModel):
    url: str = "sqlite:///.sentinel/results.db"


class SlackAlert(StrictModel):
    webhook_url: str = Field(min_length=1)


class EmailAlert(StrictModel):
    smtp_host: str = Field(min_length=1)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    from_address: str | None = None
    to: list[str] = Field(min_length=1)
    use_tls: bool = True


NotifyOn = Literal["fail", "error", "warn", "recovered"]


def _default_notify_on() -> list[NotifyOn]:
    return ["fail", "error"]


class Alerts(StrictModel):
    slack: SlackAlert | None = None
    email: EmailAlert | None = None
    notify_on: list[NotifyOn] = Field(default_factory=_default_notify_on)


class Schedule(StrictModel):
    cron: str

    @field_validator("cron")
    @classmethod
    def _five_fields(cls, value: str) -> str:
        if len(value.split()) != 5:
            raise ValueError(
                "cron must have 5 fields (minute hour day month weekday), e.g. '0 * * * *'"
            )
        return value


# --- checks ---------------------------------------------------------------


class CheckBase(StrictModel):
    name: str | None = None
    severity: Severity = "error"
    where: str | None = None
    tags: list[str] = Field(default_factory=list)


class FreshnessCheck(CheckBase):
    type: Literal["freshness"]
    column: str
    max_age: timedelta

    @field_validator("max_age", mode="before")
    @classmethod
    def _parse_max_age(cls, value: object) -> timedelta:
        return parse_duration(value)


class RowCountCheck(CheckBase):
    type: Literal["row_count"]
    min: int | None = Field(default=None, ge=0)
    max: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _bounds(self) -> RowCountCheck:
        if self.min is None and self.max is None:
            raise ValueError("set at least one of min or max")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) is greater than max ({self.max})")
        return self


class RowCountChangeCheck(CheckBase):
    type: Literal["row_count_change"]
    max_drop_pct: float | None = Field(default=None, ge=0, le=100)
    max_growth_pct: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _at_least_one(self) -> RowCountChangeCheck:
        if self.max_drop_pct is None and self.max_growth_pct is None:
            raise ValueError("set at least one of max_drop_pct or max_growth_pct")
        return self


class NotNullCheck(CheckBase):
    type: Literal["not_null"]
    column: str


class NullRateCheck(CheckBase):
    type: Literal["null_rate"]
    column: str
    max_pct: float = Field(default=0, ge=0, le=100)


class UniqueCheck(CheckBase):
    type: Literal["unique"]
    columns: list[str] = Field(min_length=1)


class AcceptedValuesCheck(CheckBase):
    type: Literal["accepted_values"]
    column: str
    values: list[str | int | float | bool] = Field(min_length=1)


class SchemaDriftCheck(CheckBase):
    type: Literal["schema_drift"]
    ignore_columns: list[str] = Field(default_factory=list)


class CustomSqlCheck(CheckBase):
    type: Literal["custom_sql"]
    name: str = Field(min_length=1)
    sql: str = Field(min_length=1)


CheckSpec = Annotated[
    FreshnessCheck
    | RowCountCheck
    | RowCountChangeCheck
    | NotNullCheck
    | NullRateCheck
    | UniqueCheck
    | AcceptedValuesCheck
    | SchemaDriftCheck
    | CustomSqlCheck,
    Field(discriminator="type"),
]

CHECK_TYPES: tuple[str, ...] = (
    "freshness",
    "row_count",
    "row_count_change",
    "not_null",
    "null_rate",
    "unique",
    "accepted_values",
    "schema_drift",
    "custom_sql",
)


# --- tables and the whole file --------------------------------------------


class TableSpec(StrictModel):
    source: str
    table: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    checks: list[CheckSpec] = Field(min_length=1)

    @field_validator("checks", mode="before")
    @classmethod
    def _unwrap_check_items(cls, value: Any) -> Any:
        """Turn `- freshness: {column: x}` into `{"type": "freshness", "column": "x"}`.

        Items that don't have this shape are passed through unchanged, so the
        discriminated union reports them with their list position intact.
        """
        if not isinstance(value, list):
            return value
        unwrapped: list[Any] = []
        for item in value:
            if isinstance(item, dict) and len(item) == 1:
                ((kind, params),) = item.items()
                if params is None:
                    params = {}
                if isinstance(params, dict):
                    unwrapped.append({**params, "type": kind})
                    continue
            unwrapped.append(item)
        return unwrapped


class SentinelConfig(StrictModel):
    version: Literal[1]
    sources: dict[str, Source] = Field(min_length=1)
    store: Store = Field(default_factory=Store)
    alerts: Alerts = Field(default_factory=Alerts)
    schedule: Schedule | None = None
    tables: list[TableSpec] = Field(min_length=1)

    def check_count(self) -> int:
        return sum(len(table.checks) for table in self.tables)
