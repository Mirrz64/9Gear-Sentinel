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
    not_null_all,
    plural,
    show_value,
)
from sentinel.config.models import UniqueCheck


def build(spec: UniqueCheck, target: TableClause) -> Executable:
    """Count key values that appear more than once. Rows with a null key are ignored."""
    cols: list[ColumnClause[Any]] = [column(name) for name in spec.columns]
    duplicates = (
        apply_where(select(*cols).select_from(target), spec)
        .where(*not_null_all(cols))
        .group_by(*cols)
        .having(func.count() > 1)
    )
    return select(func.count()).select_from(duplicates.subquery())


def evaluate(spec: UniqueCheck, row: Any, ctx: EvalContext) -> Evaluation:
    duplicates = int(row[0] or 0)
    key = ", ".join(spec.columns)
    if duplicates:
        return Evaluation(False, duplicates, f"{plural(duplicates, 'duplicate key')} in ({key})")
    return Evaluation(True, 0, f"({key}) is unique")


def sample(spec: UniqueCheck, target: TableClause) -> Executable:
    """The most repeated keys first."""
    cols: list[ColumnClause[Any]] = [column(name) for name in spec.columns]
    return (
        apply_where(select(*cols).select_from(target), spec)
        .where(*not_null_all(cols))
        .group_by(*cols)
        .having(func.count() > 1)
        .order_by(func.count().desc(), *cols)
        .limit(SAMPLE_SIZE)
    )


def describe_sample(spec: UniqueCheck, rows: Sequence[Any]) -> str:
    if len(spec.columns) == 1:
        keys = [show_value(row[0]) for row in rows]
    else:
        keys = ["(" + ", ".join(show_value(value) for value in row) + ")" for row in rows]
    return "e.g. " + ", ".join(keys)


IMPL = CheckImpl(build=build, evaluate=evaluate, sample=sample, describe_sample=describe_sample)
