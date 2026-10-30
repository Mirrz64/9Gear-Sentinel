from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.sql.expression import Executable, TableClause

from sentinel.checks.base import CheckImpl, Evaluation, apply_where, plural
from sentinel.config.models import RowCountCheck


def build(spec: RowCountCheck, target: TableClause) -> Executable:
    return apply_where(select(func.count()).select_from(target), spec)


def evaluate(spec: RowCountCheck, row: Any, now: datetime) -> Evaluation:
    count = int(row[0] or 0)
    if spec.min is not None and count < spec.min:
        return Evaluation(False, count, f"{plural(count, 'row')}, expected at least {spec.min}")
    if spec.max is not None and count > spec.max:
        return Evaluation(False, count, f"{plural(count, 'row')}, expected at most {spec.max}")
    return Evaluation(True, count, plural(count, "row"))


IMPL = CheckImpl(build=build, evaluate=evaluate)
