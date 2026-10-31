from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnClause, column, func, select
from sqlalchemy.sql.expression import Executable, TableClause

from sentinel.checks.base import (
    SAMPLE_SIZE,
    CheckImpl,
    EvalContext,
    Evaluation,
    apply_where,
    plural,
    show_value,
)
from sentinel.config.models import AcceptedValuesCheck

_SHOW_VALUES = 5


def build(spec: AcceptedValuesCheck, target: TableClause) -> Executable:
    """Count non-null rows whose value isn't in the list. Nulls are not_null's job."""
    col: ColumnClause[Any] = column(spec.column)
    query = (
        select(func.count()).select_from(target).where(col.is_not(None), col.not_in(spec.values))
    )
    return apply_where(query, spec)


def _allowed(spec: AcceptedValuesCheck) -> str:
    shown = ", ".join(str(value) for value in spec.values[:_SHOW_VALUES])
    extra = len(spec.values) - _SHOW_VALUES
    return f"{shown}, +{extra} more" if extra > 0 else shown


def evaluate(spec: AcceptedValuesCheck, row: Any, ctx: EvalContext) -> Evaluation:
    bad = int(row[0] or 0)
    if bad:
        return Evaluation(
            False, bad, f"{plural(bad, 'row')} with {spec.column} outside [{_allowed(spec)}]"
        )
    return Evaluation(True, 0, f"all {spec.column} values accepted")


def sample(spec: AcceptedValuesCheck, target: TableClause) -> Executable:
    """The most frequent unexpected values first."""
    col: ColumnClause[Any] = column(spec.column)
    query = (
        select(col)
        .select_from(target)
        .where(col.is_not(None), col.not_in(spec.values))
        .group_by(col)
        .order_by(func.count().desc(), col)
        .limit(SAMPLE_SIZE)
    )
    return apply_where(query, spec)


def describe_sample(spec: AcceptedValuesCheck, rows: Sequence[Any]) -> str:
    return "found " + ", ".join(show_value(row[0]) for row in rows)


IMPL = CheckImpl(build=build, evaluate=evaluate, sample=sample, describe_sample=describe_sample)
