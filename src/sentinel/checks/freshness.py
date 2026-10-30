from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import ColumnClause, column, func, select
from sqlalchemy.sql.expression import Executable, TableClause

from sentinel.checks.base import CheckImpl, Evaluation, apply_where
from sentinel.config.models import FreshnessCheck
from sentinel.utils.durations import format_duration


def build(spec: FreshnessCheck, target: TableClause) -> Executable:
    col: ColumnClause[Any] = column(spec.column)
    return apply_where(select(func.max(col)).select_from(target), spec)


def to_utc(value: object) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    raise TypeError(f"column is not a date or timestamp (got {type(value).__name__})")


def evaluate(spec: FreshnessCheck, row: Any, now: datetime) -> Evaluation:
    newest = row[0]
    if newest is None:
        return Evaluation(False, None, f"no values in {spec.column}; table is empty or all null")
    age = now - to_utc(newest)
    limit = format_duration(spec.max_age)
    if age.total_seconds() < 0:
        return Evaluation(True, 0.0, f"newest {spec.column} is in the future (limit {limit})")
    passed = age <= spec.max_age
    return Evaluation(
        passed,
        age.total_seconds(),
        f"newest {spec.column} is {format_duration(age)} old (limit {limit})",
    )


IMPL = CheckImpl(build=build, evaluate=evaluate)
