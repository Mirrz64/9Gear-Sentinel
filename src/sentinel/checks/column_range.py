from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnClause, ColumnElement, case, column, func, or_, select
from sqlalchemy.sql.expression import Executable, TableClause

from sentinel.checks.base import (
    SAMPLE_SIZE,
    CheckImpl,
    EvalContext,
    Evaluation,
    apply_where,
    fmt_number,
    plural,
    show_value,
)
from sentinel.config.models import ColumnRangeCheck


def _outside(spec: ColumnRangeCheck, col: ColumnClause[Any]) -> ColumnElement[bool]:
    """True for a non-null value outside the bounds. Nulls never match."""
    conditions: list[ColumnElement[bool]] = []
    if spec.min is not None:
        conditions.append(col < spec.min)
    if spec.max is not None:
        conditions.append(col > spec.max)
    return or_(*conditions)


def build(spec: ColumnRangeCheck, target: TableClause) -> Executable:
    """One row: the smallest value, the largest, and how many values are out of range."""
    col: ColumnClause[Any] = column(spec.column)
    out_of_range = case((_outside(spec, col), 1), else_=0)
    query = select(func.min(col), func.max(col), func.sum(out_of_range)).select_from(target)
    return apply_where(query, spec)


def _expected(spec: ColumnRangeCheck) -> str:
    if spec.min is not None and spec.max is not None:
        return f"between {fmt_number(spec.min)} and {fmt_number(spec.max)}"
    if spec.min is not None:
        return f"at least {fmt_number(spec.min)}"
    assert spec.max is not None
    return f"at most {fmt_number(spec.max)}"


def evaluate(spec: ColumnRangeCheck, row: Any, ctx: EvalContext) -> Evaluation:
    lowest, highest, outside = row[0], row[1], int(row[2] or 0)
    if lowest is None:
        return Evaluation(True, 0, f"no values in {spec.column} to check")

    try:
        seen = f"min {fmt_number(float(lowest))}, max {fmt_number(float(highest))}"
    except (TypeError, ValueError):
        raise TypeError(f"{spec.column} is not a numeric column") from None
    if outside:
        return Evaluation(
            False,
            outside,
            f"{plural(outside, 'value')} out of range in {spec.column} "
            f"(expected {_expected(spec)}; {seen})",
        )
    return Evaluation(True, 0, f"all values {_expected(spec)} ({seen})")


def sample(spec: ColumnRangeCheck, target: TableClause) -> Executable:
    """The most common out-of-range values first."""
    col: ColumnClause[Any] = column(spec.column)
    return (
        apply_where(select(col).select_from(target), spec)
        .where(_outside(spec, col))
        .group_by(col)
        .order_by(func.count().desc(), col)
        .limit(SAMPLE_SIZE)
    )


def describe_sample(spec: ColumnRangeCheck, rows: Sequence[Any]) -> str:
    return "e.g. " + ", ".join(show_value(row[0]) for row in rows)


IMPL = CheckImpl(build=build, evaluate=evaluate, sample=sample, describe_sample=describe_sample)
