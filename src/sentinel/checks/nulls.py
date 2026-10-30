from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ColumnClause, case, column, func, select
from sqlalchemy.sql.expression import Executable, TableClause

from sentinel.checks.base import CheckImpl, Evaluation, apply_where, plural
from sentinel.config.models import NotNullCheck, NullRateCheck


def build_not_null(spec: NotNullCheck, target: TableClause) -> Executable:
    col: ColumnClause[Any] = column(spec.column)
    query = select(func.count()).select_from(target).where(col.is_(None))
    return apply_where(query, spec)


def evaluate_not_null(spec: NotNullCheck, row: Any, now: datetime) -> Evaluation:
    nulls = int(row[0] or 0)
    if nulls:
        return Evaluation(False, nulls, f"{plural(nulls, 'null')} in {spec.column}")
    return Evaluation(True, 0, f"no nulls in {spec.column}")


def build_null_rate(spec: NullRateCheck, target: TableClause) -> Executable:
    col: ColumnClause[Any] = column(spec.column)
    query = select(
        func.count(),
        func.sum(case((col.is_(None), 1), else_=0)),
    ).select_from(target)
    return apply_where(query, spec)


def evaluate_null_rate(spec: NullRateCheck, row: Any, now: datetime) -> Evaluation:
    total = int(row[0] or 0)
    nulls = int(row[1] or 0)
    if total == 0:
        return Evaluation(True, 0.0, "table is empty; nothing to measure")
    pct = round(nulls / total * 100, 2)
    message = f"{pct}% null in {spec.column} ({nulls} of {total}), limit {spec.max_pct}%"
    return Evaluation(pct <= spec.max_pct, pct, message)


NOT_NULL = CheckImpl(build=build_not_null, evaluate=evaluate_not_null)
NULL_RATE = CheckImpl(build=build_null_rate, evaluate=evaluate_null_rate)
