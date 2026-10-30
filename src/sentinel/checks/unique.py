from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ColumnClause, column, func, select
from sqlalchemy.sql.expression import Executable, TableClause

from sentinel.checks.base import CheckImpl, Evaluation, apply_where, not_null_all, plural
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


def evaluate(spec: UniqueCheck, row: Any, now: datetime) -> Evaluation:
    duplicates = int(row[0] or 0)
    key = ", ".join(spec.columns)
    if duplicates:
        return Evaluation(False, duplicates, f"{plural(duplicates, 'duplicate key')} in ({key})")
    return Evaluation(True, 0, f"({key}) is unique")


IMPL = CheckImpl(build=build, evaluate=evaluate)
